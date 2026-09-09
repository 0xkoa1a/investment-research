"""抓取 A 股指数数据。

双通道设计:
  主通道 AkShare  —— 数据全、无需 Key，但接口偶有变动
  备通道 yfinance —— 用 000001.SS / 000300.SS 兜底

主通道失败时自动降级到备通道，保证 A 股数据不会因单一接口失效而中断。
"""

from __future__ import annotations

import pandas as pd

from inv import config as C
from inv.storage import log, retry, upsert_csv

# AkShare 代码 -> yfinance 备用代码
_FALLBACK_MAP = {
    "sh000001": "000001.SS",
    "sh000300": "000300.SS",
    "sh000905": "000905.SS",
    "sz399006": "399006.SZ",
    "sh000688": None,  # 科创50 yfinance 无对应，无备通道
}


def _via_akshare(code: str) -> pd.DataFrame | None:
    """AkShare 主通道：抓取指数日线。"""
    try:
        import akshare as ak
    except ImportError:
        log("warn", "未安装 akshare，A 股将走 yfinance 备通道")
        return None

    def _do() -> pd.DataFrame:
        df = ak.stock_zh_index_daily(symbol=code)
        if df is None or df.empty:
            raise ValueError("返回空数据")
        return df

    df = retry(_do, attempts=2, label=f"AkShare:{code}")
    if df is None or df.empty:
        return None

    df = df.rename(columns={"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"})
    if "date" not in df.columns:
        return None

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep]
    df.index.name = "date"
    return df.dropna(how="all")


def _via_yfinance(yf_code: str, start: str) -> pd.DataFrame | None:
    """yfinance 备通道。"""
    from inv.fetch_market import _download

    return _download(yf_code, start)


def fetch_all(*, start: str = C.START_DATE, only: list[str] | None = None) -> dict[str, int]:
    """抓取 config.CN_INDEXES 中全部（或指定）A 股指数并增量写盘。

    Returns:
        {字段名: 落盘总行数}
    """
    C.ensure_dirs()
    targets = only or list(C.CN_INDEXES.keys())
    result: dict[str, int] = {}

    log("info", f"A股: 开始抓取 {len(targets)} 个指数")

    for code in targets:
        meta = C.CN_INDEXES.get(code)
        if meta is None:
            log("warn", f"CN:{code} 未在 config.CN_INDEXES 登记，跳过")
            continue
        col, desc = meta

        df = _via_akshare(code)
        via = "akshare"

        if df is None:
            fb = _FALLBACK_MAP.get(code)
            if fb:
                log("warn", f"CN:{code} 主通道失败，降级到 yfinance:{fb}")
                df = _via_yfinance(fb, start)
                via = f"yf:{fb}"

        if df is None:
            log("fail", f"CN:{code} ({desc}) 两个通道均无数据")
            continue

        total, added = upsert_csv(C.RAW_CN / f"{col}.csv", df)
        result[col] = total
        log("ok", f"CN:{code:<10} {desc:<12} {total:>6} 行 (+{added})  [{via}]")

    log("info", f"A股: 完成 {len(result)}/{len(targets)}")
    return result


if __name__ == "__main__":
    fetch_all()
