"""从 Yahoo Finance 抓取市场行情（黄金、美元、美债 ETF、美股、大宗）。

落盘策略：每个 ticker 一个 CSV，保留 OHLCV 全字段（未来若要做波动率、
成交量分析不必重抓），但派生数据集默认只取收盘价。

注意 yfinance 是非官方接口，可能不稳定；storage.retry 已做指数退避，
且 upsert_csv 保证抓取失败时不会覆盖已有历史数据。
"""

from __future__ import annotations

import pandas as pd

from inv import config as C
from inv.storage import log, retry, upsert_csv


def _download(ticker: str, start: str) -> pd.DataFrame | None:
    """下载单个 ticker 的 OHLCV，规整列名与索引。"""
    try:
        import yfinance as yf
    except ImportError:
        log("fail", "未安装 yfinance，请执行 uv sync")
        return None

    def _do() -> pd.DataFrame:
        df = yf.download(
            ticker,
            start=start,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            raise ValueError("返回空数据")
        return df

    df = retry(_do, label=f"YF:{ticker}")
    if df is None or df.empty:
        return None

    # yfinance 新版返回 MultiIndex 列 (字段, ticker)，需展平
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    keep = [c for c in ("open", "high", "low", "close", "adj_close", "volume") if c in df.columns]
    df = df[keep].copy()

    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df.index.name = "date"

    return df.dropna(how="all")


def fetch_all(*, start: str = C.START_DATE, only: list[str] | None = None) -> dict[str, int]:
    """抓取 config.YF_TICKERS 中全部（或指定）品种并增量写盘。

    Returns:
        {字段名: 落盘总行数}
    """
    C.ensure_dirs()
    targets = only or list(C.YF_TICKERS.keys())
    result: dict[str, int] = {}

    log("info", f"Yahoo Finance: 开始抓取 {len(targets)} 个品种 (start={start})")

    for tk in targets:
        meta = C.YF_TICKERS.get(tk)
        if meta is None:
            log("warn", f"YF:{tk} 未在 config.YF_TICKERS 登记，跳过")
            continue
        col, desc, cls = meta

        df = _download(tk, start)
        if df is None:
            log("fail", f"YF:{tk} ({desc}) 无数据")
            continue

        total, added = upsert_csv(C.RAW_MARKET / f"{col}.csv", df)
        result[col] = total
        log("ok", f"YF:{tk:<12} {desc:<22} {total:>6} 行 (+{added})  [{cls}]")

    log("info", f"Yahoo Finance: 完成 {len(result)}/{len(targets)}")
    return result


if __name__ == "__main__":
    fetch_all()
