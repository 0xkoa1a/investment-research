"""自动生成 data/SOURCES.md 数据字典。

为什么需要这个:
  半年后回看自己的数据，最常见的困境是"这一列到底是什么口径、什么单位"。
  本模块从 config.py 的登记信息 + raw 目录的实际文件状态自动生成文档，
  保证数据字典永远与实际数据一致，不会因手工维护而腐坏。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from inv import config as C
from inv.storage import log

_FREQ_CN = {"D": "日", "W": "周", "M": "月", "Q": "季"}


def _file_status(path: Path) -> tuple[str, str, str]:
    """返回 (行数, 起始日, 结束日)；文件不存在返回占位符。"""
    if not path.exists():
        return ("—", "—", "—")
    try:
        df = pd.read_csv(path, parse_dates=["date"], index_col="date")
        if df.empty:
            return ("0", "—", "—")
        return (str(len(df)), str(df.index.min().date()), str(df.index.max().date()))
    except Exception:  # noqa: BLE001
        return ("?", "—", "—")


def generate(*, write: bool = True) -> str:
    """生成 SOURCES.md 内容。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L: list[str] = []

    L.append("# 数据字典 SOURCES")
    L.append("")
    L.append("> 本文件由 `inv.sources.generate()` 自动生成，请勿手工编辑。")
    L.append(f"> 最后生成：{now}")
    L.append("> 新增数据序列请在 `src/inv/config.py` 中登记，然后运行 `make update`。")
    L.append("")
    L.append("行数/起止日期反映 `data/raw/` 下的实际落盘状态。")
    L.append("")

    # ---- FRED ----
    L.append("## FRED（圣路易斯联储）")
    L.append("")
    L.append("来源：<https://fred.stlouisfed.org>　需免费 API Key（配置于 `.env`）")
    L.append("")
    L.append("落盘位置：`data/raw/fred/<字段名>.csv`")
    L.append(
        "最早可证 vintage：`data/raw/fred_first_release/<字段名>.csv`，保留观测期、该 vintage 的值与可用日。"
    )
    L.append("")
    L.append("| 字段名 | FRED ID | 说明 | 单位 | 原频率 | 行数 | 起始 | 最新 |")
    L.append("|---|---|---|---|---|---:|---|---|")
    for sid, (col, desc, unit, freq) in C.FRED_SERIES.items():
        n, s, e = _file_status(C.RAW_FRED / f"{col}.csv")
        fq = _FREQ_CN.get(freq, freq)
        L.append(f"| `{col}` | [{sid}](https://fred.stlouisfed.org/series/{sid}) | {desc} | {unit} | {fq} | {n} | {s} | {e} |")
    L.append("")

    # ---- Yahoo Finance ----
    L.append("## Yahoo Finance")
    L.append("")
    L.append("来源：`yfinance` 库（非官方接口，已实现重试与失败保护）")
    L.append("")
    L.append("落盘位置：`data/raw/market/<字段名>.csv`，保留 OHLCV 全字段；")
    L.append("派生数据集默认取 `adj_close`（无则取 `close`）。")
    L.append("")
    L.append("| 字段名 | Ticker | 说明 | 资产类别 | 行数 | 起始 | 最新 |")
    L.append("|---|---|---|---|---:|---|---|")
    for tk, (col, desc, cls) in C.YF_TICKERS.items():
        n, s, e = _file_status(C.RAW_MARKET / f"{col}.csv")
        L.append(f"| `{col}` | `{tk}` | {desc} | {cls} | {n} | {s} | {e} |")
    L.append("")

    # ---- A股 ----
    L.append("## A股指数")
    L.append("")
    L.append("主通道：AkShare（`stock_zh_index_daily`，无需 Key）")
    L.append("备通道：yfinance（主通道失败时自动降级）")
    L.append("")
    L.append("落盘位置：`data/raw/cn/<字段名>.csv`")
    L.append("")
    L.append("| 字段名 | 代码 | 说明 | 行数 | 起始 | 最新 |")
    L.append("|---|---|---|---:|---|---|")
    for code, (col, desc) in C.CN_INDEXES.items():
        n, s, e = _file_status(C.RAW_CN / f"{col}.csv")
        L.append(f"| `{col}` | `{code}` | {desc} | {n} | {s} | {e} |")
    L.append("")

    # ---- 派生字段命名约定 ----
    L.append("## 派生字段命名约定")
    L.append("")
    L.append("由 `inv.dataset.add_derived()` 生成，存于 `data/processed/`（不进版本库，可随时重建）。")
    L.append("默认视图按最早可证可用日对齐；`observation` 文件仅用于明确的描述性观测期分析。")
    L.append("")
    L.append("| 前缀/模式 | 含义 | 计算方式 | 示例 |")
    L.append("|---|---|---|---|")
    L.append("| `ret_<x>` | 对数收益率 | `ln(x_t / x_{t-1})` | `ret_gold` |")
    L.append("| `d_<x>` | 一阶差分 | `x_t - x_{t-1}`，单位=百分点 | `d_real10y` |")
    L.append("| `ratio_<a>_<b>` | 比价 | `a / b` | `ratio_gold_silver` |")
    L.append("| `<x>_implied` | 推算值 | 见 `dataset.py` 注释 | `real10y_implied` |")
    L.append("")
    L.append("**为什么价格用对数收益、利率用差分**：")
    L.append("")
    L.append("- 价格的变化幅度应以比例衡量，且对数收益可跨期相加，便于重采样。")
    L.append("- 利率本身已是百分比，从 2% 到 3% 是「上升 1 个百分点」，而非「上涨 50%」，")
    L.append("  因此用绝对差分才有经济含义。")
    L.append("")

    # ---- 数据集文件 ----
    L.append("## 派生数据集")
    L.append("")
    L.append("| 文件 | 频率 | 重采样规则 |")
    L.append("|---|---|---|")
    L.append("| `processed/macro_daily.csv` | SPX 实际交易日 | 最早可证可用日后的下一交易时段生效，按频率限制有效期 |")
    L.append("| `processed/macro_weekly.csv` | 周（周五） | `ret_*`/`d_*` 累加，其余取区间末值 |")
    L.append("| `processed/macro_monthly.csv` | 月末 | 同上 |")
    L.append("| `processed/macro_observation_*.csv` | 日/周/月 | 按观测期对齐的描述性最新修订值，不用于回测 |")
    L.append("")
    L.append("**时点口径**：FRED 的观测日期不是发布时间。默认数据集使用 ALFRED 留存的最早可证 vintage 日，")
    L.append("并在缺少日内时间时从下一 SPX 交易时段保守生效；它不声称等于档案覆盖前的真实历史首发时刻。市场价格不前向填充，")
    L.append("宏观值按日/周/月/季分别在 7/21/62/140 个自然日后失效。")
    L.append("")

    content = "\n".join(L) + "\n"

    if write:
        path = C.DATA / "SOURCES.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        log("ok", f"生成 {path.relative_to(C.ROOT)}")

    return content


if __name__ == "__main__":
    generate()
