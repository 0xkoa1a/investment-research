#!/usr/bin/env python
"""构建中国挖掘机与宏观年度图表数据（2006—2025）。

输出：data/raw/cn_macro/excavator_macro_annual.csv

脚本把公开月度序列聚合为年度数据，并把仅按年度发布的历史序列整理到
同一张可审计的数据表。报告渲染只读取落盘 CSV，不在渲染时联网。
"""

from __future__ import annotations

from pathlib import Path

import akshare as ak
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "raw" / "cn_macro" / "excavator_macro_annual.csv"
YEARS = pd.Index(range(2006, 2026), name="year")

CHINA_DATA_API = "https://chinadata.live/api/v2/data"

# 国家统计局年度累计产量。2007—2009 由完整当月值加总；2010—2025
# 采用公开年度累计表，避免 2013 年后 1—2 月当月值不单列造成漏算。
EXCAVATOR_OUTPUT = {
    2007: 28_765,
    2008: 55_541,
    2009: 107_903,
    2010: 192_811,
    2011: 194_961,
    2012: 142_162,
    2013: 148_877,
    2014: 125_301,
    2015: 92_592,
    2016: 111_395,
    2017: 194_606,
    2018: 269_532,
    2019: 266_299,
    2020: 401_096,
    2021: 362_029,
    2022: 306_950,
    2023: 235_765,
    2024: 299_338,
    2025: 379_643,
}

# 2006—2019：工程机械工业协会、智研咨询整理；2020—2025：协会年度快报。
EXCAVATOR_SALES = {
    2006: 49_625,
    2007: 71_241,
    2008: 82_975,
    2009: 101_559,
    2010: 179_296,
    2011: 193_891,
    2012: 130_624,
    2013: 126_296,
    2014: 103_227,
    2015: 60_514,
    2016: 73_390,
    2017: 144_867,
    2018: 203_420,
    2019: 235_693,
    2020: 327_605,
    2021: 342_784,
    2022: 261_346,
    2023: 195_018,
    2024: 201_131,
    2025: 235_257,
}

# 房屋新开工面积，万平方米。2005 用于计算 2006 年同比。
REAL_ESTATE_NEW_STARTS = {
    2005: 68_064.44,
    2006: 79_252.83,
    2007: 95_401.53,
    2008: 102_553.37,
    2009: 116_422.05,
    2010: 163_646.87,
    2011: 191_236.87,
    2012: 177_333.62,
    2013: 201_207.84,
    2014: 179_592.49,
    2015: 154_453.68,
    2016: 166_928.13,
    2017: 178_653.77,
    2018: 209_537.16,
    2019: 227_153.58,
    2020: 224_433.13,
    2021: 198_895.05,
    2022: 120_107.43,
    2023: 95_957.9564,
    2024: 73_892.8408,
    2025: 58_770.0,
}

# 国家统计局公布的全年名义增速。早期公开资料口径不连续，因此不补造
# 2006—2008；图表保留空值，从 2009 年开始显示。
INFRASTRUCTURE_INVESTMENT_YOY = {
    2009: 44.3,
    2010: 16.7,
    2011: 5.9,
    2012: 13.3,
    2013: 21.2,
    2014: 21.5,
    2015: 17.2,
    2016: 17.4,
    2017: 19.0,
    2018: 3.8,
    2019: 3.8,
    2020: 0.9,
    2021: 0.4,
    2022: 9.4,
    2023: 5.9,
    2024: 4.4,
    2025: -2.2,
}

# 国家统计局年度固定资产投资分行业增速。
MINING_INVESTMENT_YOY = {
    2006: 28.9,
    2007: 26.9,
    2008: 31.5,
    2009: 18.2,
    2010: 18.1,
    2011: 21.4,
    2012: 11.8,
    2013: 10.9,
    2014: 0.7,
    2015: -8.8,
    2016: -20.4,
    2017: -10.0,
    2018: 4.1,
    2019: 24.1,
    2020: -14.1,
    2021: 10.9,
    2022: 4.5,
    2023: 2.1,
    2024: 10.5,
    2025: 2.5,
}


def china_data_series(slug: str) -> pd.DataFrame:
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
    return frame.sort_values("date")


def annual_monthly(frame: pd.DataFrame, how: str) -> pd.Series:
    counts = frame.loc[frame["date"].dt.year <= 2025].groupby(
        frame.loc[frame["date"].dt.year <= 2025, "date"].dt.year
    )["value"].count()
    incomplete = counts.loc[(counts.index >= 2007) & (counts < 12)]
    if not incomplete.empty:
        raise ValueError(f"月度序列存在不完整年度：{incomplete.to_dict()}")
    grouped = frame.assign(year=frame["date"].dt.year).query("year <= 2025").groupby("year")["value"]
    return grouped.sum() if how == "sum" else grouped.mean()


def li_keqiang_components() -> pd.DataFrame:
    """构建电力、铁路货运和人民币贷款余额同比三项年度序列。"""
    electricity = ak.macro_china_society_electricity().copy()
    electricity["year"] = electricity["统计时间"].astype(str).str.split(".").str[0].astype(int)
    electricity["month"] = electricity["统计时间"].astype(str).str.split(".").str[1].astype(int)
    elec_yoy = (
        electricity.loc[electricity["month"].eq(12), ["year", "第二产业用电量同比"]]
        .dropna()
        .drop_duplicates("year", keep="last")
        .set_index("year")["第二产业用电量同比"]
        .astype(float)
    )

    traffic = ak.macro_china_society_traffic_volume().copy()
    traffic["year"] = traffic["统计时间"].astype(str).str.split(".").str[0].astype(int)
    traffic["month"] = traffic["统计时间"].astype(str).str.split(".").str[1].astype(int)
    rail_yoy = (
        traffic.loc[
            traffic["统计对象"].eq("铁路") & traffic["month"].eq(12),
            ["year", "货运量同比增长"],
        ]
        .dropna()
        .drop_duplicates("year", keep="first")
        .set_index("year")["货运量同比增长"]
        .astype(float)
    )

    credit = ak.macro_china_new_financial_credit().copy()
    credit["year"] = credit["月份"].astype(str).str[:4].astype(int)
    annual_credit = (
        credit.loc[credit["月份"].astype(str).str.contains("12月份"), ["year", "累计"]]
        .dropna()
        .drop_duplicates("year", keep="first")
        .set_index("year")["累计"]
        .astype(float)
        .sort_index()
    )

    # 贷款余额单位为亿元。以人民银行公布的 2025 年末人民币贷款余额
    # 271.91 万亿元为锚，按年度新增贷款向前回推期末余额。
    loan_stock = {2025: 2_719_100.0}
    for year in range(2025, 2007, -1):
        loan_stock[year - 1] = loan_stock[year] - annual_credit.loc[year]
    loan_yoy = pd.Series(
        {year: annual_credit.loc[year] / loan_stock[year - 1] * 100 for year in range(2008, 2026)},
        name="loan_balance_yoy_pct",
    )
    # 2006、2007 直接采用人民银行/国家统计资料公布的年末增速。
    loan_yoy.loc[2006] = 15.1
    loan_yoy.loc[2007] = 16.1

    out = pd.concat(
        [
            elec_yoy.rename("secondary_electricity_yoy_pct"),
            rail_yoy.rename("rail_freight_yoy_pct"),
            loan_yoy,
        ],
        axis=1,
    ).reindex(YEARS)
    if out.isna().any().any():
        raise ValueError(f"克强指数构成存在缺值：\n{out.loc[out.isna().any(axis=1)]}")
    out["li_keqiang_index_pct"] = (
        0.4 * out["secondary_electricity_yoy_pct"]
        + 0.2 * out["rail_freight_yoy_pct"]
        + 0.4 * out["loan_balance_yoy_pct"]
    )
    return out


def main() -> None:
    production = pd.Series(EXCAVATOR_OUTPUT, dtype=float)
    pmi = annual_monthly(china_data_series("china-pmi"), "mean")
    li = li_keqiang_components()

    out = pd.DataFrame(index=YEARS)
    out["excavator_output_units"] = production.reindex(YEARS)
    out["manufacturing_pmi_annual_mean"] = pmi.reindex(YEARS)
    out = out.join(li)

    sales = pd.Series(EXCAVATOR_SALES, dtype=float).sort_index()
    sales_yoy = sales.pct_change() * 100
    sales_yoy.loc[2006] = 46.6  # 同一协会口径披露的 2006 年同比。
    out["excavator_sales_units"] = sales.reindex(YEARS)
    out["excavator_sales_yoy_pct"] = sales_yoy.reindex(YEARS)

    starts = pd.Series(REAL_ESTATE_NEW_STARTS, dtype=float).sort_index()
    out["real_estate_new_starts_10k_sqm"] = starts.reindex(YEARS)
    out["real_estate_new_starts_yoy_pct"] = (starts.pct_change() * 100).reindex(YEARS)
    out["infrastructure_investment_yoy_pct"] = pd.Series(
        INFRASTRUCTURE_INVESTMENT_YOY, dtype=float
    ).reindex(YEARS)
    out["mining_investment_yoy_pct"] = pd.Series(MINING_INVESTMENT_YOY, dtype=float).reindex(YEARS)

    required = [
        "manufacturing_pmi_annual_mean",
        "li_keqiang_index_pct",
        "excavator_sales_yoy_pct",
        "real_estate_new_starts_yoy_pct",
        "mining_investment_yoy_pct",
    ]
    if out[required].isna().any().any():
        raise ValueError(f"核心图表序列存在缺值：\n{out[required].isna().sum()}")
    if out.loc[2007:2025, "excavator_output_units"].isna().any():
        raise ValueError("挖掘机产量应完整覆盖 2007—2025")
    if pd.notna(out.loc[2006, "excavator_output_units"]):
        raise ValueError("2006 年缺少同口径挖掘机产量，不应人工补值")
    if out["infrastructure_investment_yoy_pct"].notna().sum() != 17:
        raise ValueError("基建投资同比应覆盖 2009—2025 共 17 年")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out.round(4).to_csv(OUTPUT, encoding="utf-8")
    print(f"已写入 {OUTPUT.relative_to(ROOT)}：{len(out)} 年 × {len(out.columns)} 列")


if __name__ == "__main__":
    main()
