"""多源数据合并、频率对齐、派生指标计算。

宏观研究最易出错之处在于**频率混用**：金价是日频、CPI 是月频、GDP 是季频。
本模块的处理原则:

  1. 默认数据集按信息可用日对齐到真实 SPX 交易日。FRED 观测期与最早可证
     vintage 日期分开保存，避免把月初标记的 CPI 当成月初已经可知。

  2. 前向填充设上限（低频数据不无限延伸），避免陈旧数据伪装成当前值。

  3. 重采样到周/月时，价格取区间最后值，收益率取区间累计。

  4. 派生指标（收益率、实际利率变动等）在对齐之后统一计算，
     保证所有分析基于同一份 processed 数据，不会各算各的。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from inv import config as C
from inv.storage import log, read_all_in_dir, write_csv

# ---------------------------------------------------------------------------
# 载入 raw
# ---------------------------------------------------------------------------


def load_fred() -> pd.DataFrame:
    """载入所有 FRED 序列，合并为宽表（列名 = 字段名）。"""
    frames = read_all_in_dir(C.RAW_FRED)
    if not frames:
        log("warn", "data/raw/fred 为空")
        return pd.DataFrame()
    cols = [df.iloc[:, [0]].rename(columns={df.columns[0]: name}) for name, df in frames.items()]
    out = pd.concat(cols, axis=1).sort_index()
    log("ok", f"载入 FRED {len(out.columns)} 个字段, {len(out)} 行")
    return out


def load_fred_releases() -> pd.DataFrame:
    """载入每个观测期的最早可证 vintage，并以 available_date 作为索引。"""
    frames: list[pd.DataFrame] = []
    for path in sorted(C.RAW_FRED_RELEASES.glob("*.csv")):
        frame = pd.read_csv(
            path,
            parse_dates=["observation_date", "available_date"],
        )
        value_cols = [column for column in frame.columns if column not in {"observation_date", "available_date"}]
        if len(value_cols) != 1:
            raise ValueError(f"{path.name}: vintage 文件必须只有一个数值字段")
        column = value_cols[0]
        current = (
            frame.dropna(subset=["observation_date", "available_date", column])
            .sort_values(["available_date", "observation_date"])
            .drop_duplicates("available_date", keep="last")
            .set_index("available_date")[[column]]
        )
        frames.append(current)
    if not frames:
        log("warn", "data/raw/fred_first_release 为空")
        return pd.DataFrame()
    out = pd.concat(frames, axis=1).sort_index()
    log("ok", f"载入 FRED vintage {len(out.columns)} 个字段, {len(out)} 行")
    return out


def load_prices() -> pd.DataFrame:
    """载入市场行情与 A 股，只取收盘价，合并为宽表。"""
    out_cols: list[pd.DataFrame] = []
    for d in (C.RAW_MARKET, C.RAW_CN):
        for name, df in read_all_in_dir(d).items():
            price_col = "adj_close" if "adj_close" in df.columns else "close"
            if price_col not in df.columns:
                continue
            out_cols.append(df[[price_col]].rename(columns={price_col: name}))
    if not out_cols:
        log("warn", "data/raw/market 与 data/raw/cn 均为空")
        return pd.DataFrame()
    out = pd.concat(out_cols, axis=1).sort_index()
    log("ok", f"载入行情 {len(out.columns)} 个品种, {len(out)} 行")
    return out


# ---------------------------------------------------------------------------
# 对齐：可用日视图与描述性观测期视图
# ---------------------------------------------------------------------------


def _calendar(prices: pd.DataFrame, column: str = "spx") -> pd.DatetimeIndex:
    if column not in prices.columns:
        raise ValueError(f"缺少交易日历锚点 {column}；不能用工作日伪造交易日")
    calendar = pd.DatetimeIndex(prices[column].dropna().index.unique()).sort_values()
    if calendar.empty:
        raise ValueError(f"交易日历锚点 {column} 为空")
    calendar.name = "date"
    return calendar


def _max_age(column: str) -> int:
    meta = C.series_meta().get(column)
    frequency = meta.get("frequency", "D") if meta else "D"
    return C.FRED_MAX_AGE_DAYS.get(frequency, 7)


def _align_macro_series(
    series: pd.Series,
    calendar: pd.DatetimeIndex,
    *,
    next_session: bool,
) -> pd.Series:
    values = series.dropna().sort_index()
    if values.empty:
        return pd.Series(index=calendar, dtype="float64", name=series.name)
    side = "right" if next_session else "left"
    positions = calendar.searchsorted(values.index, side=side)
    valid = positions < len(calendar)
    activated = pd.Series(values.to_numpy()[valid], index=calendar[positions[valid]], name=series.name)
    activated = activated[~activated.index.duplicated(keep="last")]
    aligned = activated.reindex(calendar).ffill()
    source_dates = pd.Series(activated.index, index=activated.index).reindex(calendar).ffill()
    age = pd.Series(calendar, index=calendar) - source_dates
    return aligned.mask(age.dt.days > _max_age(str(series.name)))


def align_available(fred_releases: pd.DataFrame, prices: pd.DataFrame, *, calendar_col: str = "spx") -> pd.DataFrame:
    """Build an end-of-session point-in-time panel from recorded vintage dates."""
    if fred_releases.empty:
        raise ValueError("缺少 FRED vintage 数据；请先运行 make update")
    calendar = _calendar(prices, calendar_col)
    output = prices.reindex(calendar)
    for column in fred_releases.columns:
        # FRED only gives a release date, not a reliable intraday timestamp.
        # Activate conservatively from the following observed market session.
        output[column] = _align_macro_series(fred_releases[column], calendar, next_session=True)
    log("ok", f"按可用日对齐: {len(output)} 行 × {len(output.columns)} 列")
    return output


def align_observation(fred: pd.DataFrame, prices: pd.DataFrame, *, calendar_col: str = "spx") -> pd.DataFrame:
    """Build an explicitly descriptive panel aligned by observation period."""
    calendar = _calendar(prices, calendar_col)
    output = prices.reindex(calendar)
    for column in fred.columns:
        output[column] = _align_macro_series(fred[column], calendar, next_session=False)
    log("ok", f"按观测期对齐: {len(output)} 行 × {len(output.columns)} 列")
    return output


# ---------------------------------------------------------------------------
# 派生指标
# ---------------------------------------------------------------------------

# 需要计算对数收益率的价格类字段。
# Yahoo/AkShare 注册表中的字段天然是行情序列，自动纳入，避免新增 ticker 后
# 忘记同步维护另一份名单。FRED 同时包含利率、流量和价格，只有明确属于
# 市场价格/指数的字段在这里显式登记，避免按单位做脆弱推断。
_FRED_PRICE_FIELDS = ["usd_broad", "usd_afe", "usdcny", "wti"]
_REGISTERED_MARKET_FIELDS = (
    [meta[0] for meta in C.YF_TICKERS.values()]
    + [meta[0] for meta in C.CN_INDEXES.values()]
)
_RETURN_COLS = list(dict.fromkeys(_FRED_PRICE_FIELDS + _REGISTERED_MARKET_FIELDS))

# 需要计算一阶差分的利率类字段（利率变动用绝对差，不用收益率）。
# 这里刻意显式维护：FRED 的百分比字段还包含失业率等宏观水平，不能自动推断。
_DIFF_COLS = [
    "ust2y", "ust10y", "ust30y",
    "real10y", "real5y",
    "breakeven10y", "fwd5y5y",
    "curve_10y2y", "curve_10y3m",
    "ffr_effective", "iorb",
    "hy_spread",
]


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """添加派生列：对数收益率、利率一阶差分、常用比价。

    命名约定:
        ret_<x>   : x 的日对数收益率
        d_<x>     : x 的日一阶差分（利率，单位 = 百分点）
        ratio_a_b : a/b 比价
    """
    out = df.copy()

    # 价格 -> 对数收益率
    for c in _RETURN_COLS:
        if c in out.columns:
            s = out[c].where(out[c] > 0).dropna()
            out[f"ret_{c}"] = np.log(s).diff().reindex(out.index)

    # 利率 -> 一阶差分（百分点）
    for c in _DIFF_COLS:
        if c in out.columns:
            out[f"d_{c}"] = out[c].diff()

    # 常用比价
    if {"gold", "silver"}.issubset(out.columns):
        out["ratio_gold_silver"] = out["gold"] / out["silver"]
    if {"gold", "spx"}.issubset(out.columns):
        out["ratio_gold_spx"] = out["gold"] / out["spx"]
    if {"ust10y", "breakeven10y"}.issubset(out.columns) and "real10y" not in out.columns:
        # 缺 TIPS 数据时用名义收益率减通胀预期近似实际利率
        out["real10y_implied"] = out["ust10y"] - out["breakeven10y"]

    n_new = len(out.columns) - len(df.columns)
    log("ok", f"新增 {n_new} 个派生字段")
    return out


# ---------------------------------------------------------------------------
# 重采样
# ---------------------------------------------------------------------------


def resample(df: pd.DataFrame, freq: str = "W-FRI") -> pd.DataFrame:
    """重采样到低频。

    规则:
        ret_* : 区间内累加（对数收益可加）
        d_*   : 区间内累加（差分可加）
        其他   : 取区间最后一个有效值

    Args:
        freq: pandas 频率字符串，如 "W-FRI"（周五收盘）、"ME"（月末）。
    """
    if df.empty:
        return df

    agg: dict[str, str] = {}
    for c in df.columns:
        if c.startswith(("ret_", "d_")):
            agg[c] = "sum"
        else:
            agg[c] = "last"

    out = df.resample(freq).agg(agg)
    # sum 会把全 NaN 区间变成 0，需还原为 NaN
    for c in df.columns:
        if agg[c] == "sum":
            valid = df[c].notna().resample(freq).sum()
            out.loc[valid == 0, c] = np.nan

    out.index.name = "date"
    log("ok", f"重采样到 {freq}: {len(out)} 行")
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def build(*, write: bool = True) -> dict[str, pd.DataFrame]:
    """构建全部派生数据集：日频 / 周频 / 月频。

    Returns:
        {"daily": df, "weekly": df, "monthly": df}
    """
    C.ensure_dirs()
    log("info", "开始构建数据集")

    fred = load_fred()
    fred_releases = load_fred_releases()
    prices = load_prices()

    daily = align_available(fred_releases, prices)
    observation_daily = align_observation(fred, prices)
    if daily.empty or observation_daily.empty:
        log("fail", "无可用数据，请先运行 scripts/update_all.py 抓取数据")
        return {}

    daily = add_derived(daily)
    observation_daily = add_derived(observation_daily)
    weekly = resample(daily, "W-FRI")
    monthly = resample(daily, "ME")
    observation_weekly = resample(observation_daily, "W-FRI")
    observation_monthly = resample(observation_daily, "ME")

    if write:
        write_csv(C.MACRO_DAILY, daily)
        write_csv(C.MACRO_WEEKLY, weekly)
        write_csv(C.MACRO_MONTHLY, monthly)
        write_csv(C.MACRO_OBSERVATION_DAILY, observation_daily)
        write_csv(C.MACRO_OBSERVATION_WEEKLY, observation_weekly)
        write_csv(C.MACRO_OBSERVATION_MONTHLY, observation_monthly)

    return {
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "observation_daily": observation_daily,
        "observation_weekly": observation_weekly,
        "observation_monthly": observation_monthly,
    }


def load(freq: str = "daily", *, view: str = "asof_close") -> pd.DataFrame:
    """载入已构建的数据集，供图表与研究脚本调用。

    Args:
        freq: "daily" | "weekly" | "monthly"
        view: "asof_close"（默认，按最早可证可用日）| "observation"（描述性观测期）
    """
    available_paths = {
        "daily": C.MACRO_DAILY,
        "weekly": C.MACRO_WEEKLY,
        "monthly": C.MACRO_MONTHLY,
    }
    observation_paths = {
        "daily": C.MACRO_OBSERVATION_DAILY,
        "weekly": C.MACRO_OBSERVATION_WEEKLY,
        "monthly": C.MACRO_OBSERVATION_MONTHLY,
    }
    if view not in {"asof_close", "observation"}:
        raise ValueError("view 必须是 asof_close 或 observation")
    paths = available_paths if view == "asof_close" else observation_paths
    if freq not in paths:
        raise ValueError("freq 必须是 daily、weekly 或 monthly")
    path = paths[freq]
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 不存在。请先运行:\n"
            f"  uv run python scripts/update_all.py\n"
            f"  uv run python scripts/build_dataset.py"
        )
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return df.sort_index()


if __name__ == "__main__":
    build()
