#!/usr/bin/env python
"""构建挖掘机产量、制造业 PMI 与克强指数的月度快照。

输出：data/raw/cn_macro/excavator_macro_monthly.csv

国家统计局自 2013 年起通常只披露 1—2 月累计产量，不单列 1 月、
2 月当月值。快照同时保留公开当月值与 1—2 月合计，图表端据此计算
严格覆盖过去 12 个日历月的累计产量同比，不对缺失月份做插值。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "raw" / "cn_macro" / "excavator_macro_monthly.csv"
LI_KEQIANG = ROOT / "data" / "raw" / "cn_macro" / "li_keqiang_index_cme_digitized.csv"
CHINA_DATA_API = "https://chinadata.live/api/v2/data"

# 国家统计局口径的 1—2 月累计产量。2013 年后多数年份不再单列
# 1 月和 2 月当月值；2015 年虽披露 2 月当月值，滚动 12 个月仍使用
# 同口径的 1—2 月累计值。
JAN_FEB_OUTPUT = {
    2013: 19_494,
    2014: 25_616,
    2015: 17_217,
    2016: 14_358,
    2017: 22_381,
    2018: 34_283,
    2019: 49_534,
    2020: 27_629,
    2021: 71_089,
    2022: 62_650,
    2023: 40_816,
    2024: 40_638,
    2025: 47_015,
    2026: 63_566,
}


def china_data_series(slug: str) -> pd.Series:
    """读取 China Data Portal 对国家统计局月度数据的镜像。"""
    response = requests.get(
        f"{CHINA_DATA_API}/{slug}",
        headers={"User-Agent": "investment-research/0.1"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"China Data Portal 返回失败：{slug}")
    frame = pd.DataFrame(payload["data"]["data"])
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m")
    frame["value"] = pd.to_numeric(frame["value"], errors="raise")
    if frame["date"].duplicated().any():
        raise ValueError(f"{slug} 存在重复月份")
    return frame.sort_values("date").set_index("date")["value"]


def main() -> None:
    excavator = china_data_series("china-excavator-production")
    pmi = china_data_series("china-pmi")
    li = pd.read_csv(LI_KEQIANG, parse_dates=["date"]).set_index("date")[
        "li_keqiang_index_yoy_pct_digitized"
    ]

    if excavator.index.min() != pd.Timestamp("2007-01-01"):
        raise ValueError("挖掘机产量起始月份应为 2007-01")
    if pmi.index.min() != pd.Timestamp("2005-01-01"):
        raise ValueError("制造业 PMI 起始月份应为 2005-01")
    expected_li = pd.date_range("2005-01-01", "2024-03-01", freq="MS")
    if not li.index.equals(expected_li):
        raise ValueError("数字化克强指数应完整覆盖 2005-01—2024-03")

    index = pd.date_range(
        min(excavator.index.min(), pmi.index.min(), li.index.min()),
        max(excavator.index.max(), pmi.index.max(), li.index.max()),
        freq="MS",
        name="date",
    )
    out = pd.DataFrame(index=index)
    out["excavator_output_units"] = excavator.reindex(index)
    out["excavator_jan_feb_combined_units"] = pd.NA
    for year, value in JAN_FEB_OUTPUT.items():
        out.loc[pd.Timestamp(year=year, month=2, day=1), "excavator_jan_feb_combined_units"] = value
    out["excavator_jan_feb_combined_units"] = pd.to_numeric(
        out["excavator_jan_feb_combined_units"], errors="coerce"
    )
    out["manufacturing_pmi"] = pmi.reindex(index)
    out["li_keqiang_index_yoy_pct_digitized"] = li.reindex(index)

    if out.loc[pmi.index.min():pmi.index.max(), "manufacturing_pmi"].isna().any():
        raise ValueError("制造业 PMI 月度序列存在缺值")
    if out["excavator_jan_feb_combined_units"].notna().sum() != len(JAN_FEB_OUTPUT):
        raise ValueError("挖掘机 1—2 月累计产量不完整")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT, encoding="utf-8", float_format="%.2f")
    print(
        f"已写入 {OUTPUT.relative_to(ROOT)}：{len(out)} 月；"
        f"挖掘机截至 {excavator.index.max():%Y-%m}，PMI 截至 {pmi.index.max():%Y-%m}"
    )


if __name__ == "__main__":
    main()
