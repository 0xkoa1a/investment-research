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

    L.extend([
        "## 黄金研究固定快照", "",
        "`scripts/update_gold.py` 显式抓取或读取缓存，按信息截止时间保存独立快照；不更新以上共享原始数据。",
        "来源在 `config.GOLD_RESEARCH_FRED_IDS` 与 `config.GOLD_RESEARCH_CANDIDATES` 中登记。",
        "已确认采用 `gold`（COMEX 黄金期货，`GC=F`）作为主研究对象；`xauusd` 留作补充参照。",
        "`--futures-review` 复用市场下载器，在忽略缓存保存定时行情快照；公开目录保存覆盖、哈希和口径缺口。", "",
        "`--intraday` 通过 Yahoo/yfinance 定向取得五分钟 OHLCV，配置见 `config.GOLD_RESEARCH_INTRADAY`。",
        "Phase 1 日内图使用 `GCZ26.CMX` 十二月合约，长历史仍为 `GC=F` 日线；两者分别计算、不拼接。",
        "Yahoo 时间标签按柱起点处理，图中使用五分钟后的区间结束时刻（纽约时间）；不当作交易所结算价。",
        "原始响应、清洗后行情与哈希保存在忽略缓存；公开核验记录为 `reviews/intraday-<UTC截止时间>.json`。",
        "当前选定日内输入见 `phase1/intraday-input.json`；缺口不填补，节假日的缺失与休市分开核验。", "",
        "`--drivers` 固定 Phase 2 的 DXY、WTI期货、FedWatch分会议概率与GLD持金量；",
        "只有 `--drivers --refresh` 联网更新 `config.GOLD_RESEARCH_DRIVER_MARKETS` 中的两个Yahoo品种，",
        "FedWatch与GLD读取已取得的导出缓存。完整商业数据保留在忽略缓存，选定哈希与覆盖见 `phase2/inputs.json`。",
        "驱动分析按共同观测日计算，明确缩短后的截止日；CFTC按公布时间过滤，ETF与持仓保持原频率。",
        "WGC月报等后补证据及公开时间限制见 `phase2/evidence.json`；统计和图表均可离线重算。", "",
        "- `data/raw/gold-outlook/snapshots/<UTC截止时间>/coverage.csv`：实际覆盖、缺口和来源。",
        "- 同目录 `manifest.json`：输入版本、抓取时间、公开文件哈希与阶段状态。",
        "- FRED 使用研究截止时间之前最后一个完整芝加哥日的 vintage；`known_by_at` 只给可知上界。",
        "- CFTC 使用下载时的年度档案；已核验的公布时间单独记录，未知时间留空，不冒充历史初版。",
        "- 候选商业数据的公开权限未确认时，只保存核验记录，不发布完整数值。",
        "- 本研究不使用 SPX 日历裁剪黄金日期，普通站点构建不联网更新快照。", "",
    ])

    content = "\n".join(L) + "\n"

    if write:
        path = C.DATA / "SOURCES.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        log("ok", f"生成 {path.relative_to(C.ROOT)}")

    return content


if __name__ == "__main__":
    generate()
