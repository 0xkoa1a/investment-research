"""从 FRED（圣路易斯联储）抓取宏观与利率序列。

每个序列单独落一个 CSV 到 data/raw/fred/，便于:
  - Git diff 可读（一次更新只改动少数文件）
  - 单序列出问题不影响其他序列
  - 未来增删序列无需重建整个数据集

无 API Key 时优雅降级：打印申请指引并返回空结果，不阻塞整体流程。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from inv import config as C
from inv.storage import log, read_series_csv, retry, to_single_col, upsert_csv, write_csv

FRED_OBSERVATION_LIMIT = 100_000


def _client():
    """构造 FRED 客户端；无 Key 返回 None。"""
    key = C.fred_api_key()
    if key is None:
        log("skip", "FRED 抓取跳过 —— " + C.FRED_KEY_HELP.replace("\n", "\n       "))
        return None
    try:
        from fredapi import Fred
    except ImportError:
        log("fail", "未安装 fredapi，请执行 uv sync")
        return None
    return Fred(api_key=key)


def fetch_one(series_id: str, *, start: str = C.START_DATE) -> pd.DataFrame | None:
    """抓取单个 FRED 序列，返回列名为项目内部字段名的 DataFrame。"""
    fred = _client()
    if fred is None:
        return None
    col = C.FRED_SERIES.get(series_id, (series_id.lower(),))[0]
    raw = retry(
        lambda: fred.get_series(series_id, observation_start=start),
        label=f"FRED:{series_id}",
    )
    return to_single_col(raw, col)


def _fred_api_json(fred, endpoint: str, **parameters) -> dict:
    """Call one official FRED JSON endpoint with the configured client key."""
    query = urlencode({"api_key": fred.api_key, "file_type": "json", **parameters})
    url = f"https://api.stlouisfed.org/fred/{endpoint}?{query}"
    try:
        with urlopen(url, timeout=120) as response:  # noqa: S310 - fixed HTTPS host
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        if "does not exist in ALFRED" in body:
            return {"vintage_dates": []}
        raise


def _first_releases(
    fred,
    series_id: str,
    col: str,
    *,
    frequency: str,
    latest: pd.DataFrame,
    vintage_start: str = C.START_DATE,
    include_earliest_snapshot: bool = True,
) -> pd.DataFrame | None:
    """Return the earliest recorded vintage for each post-1990 observation.

    ``output_type=4`` returns initial releases without downloading every later
    revision. A snapshot at the series' earliest ALFRED vintage supplements
    observations that were backfilled when the archived series was introduced.
    """
    vintage_payload = retry(
        lambda: _fred_api_json(
            fred,
            "series/vintagedates",
            series_id=series_id,
            sort_order="asc",
            limit=1,
        ),
        label=f"FRED earliest vintage:{series_id}",
    )
    if vintage_payload is None:
        return None
    vintage_rows = vintage_payload.get("vintage_dates", [])
    if not vintage_rows:
        if frequency in {"D", "W"}:
            fallback = latest[[col]].copy()
            fallback.insert(0, "available_date", fallback.index)
            fallback.index.name = "observation_date"
            log("warn", f"FRED:{series_id} 无 ALFRED vintage；按观测日记录并在数据集中延后一交易时段")
            return fallback
        log("warn", f"FRED:{series_id} 无 ALFRED vintage；{frequency} 频序列仅保留观测值，不推测可用日期")
        return pd.DataFrame(columns=["available_date", col]).rename_axis("observation_date")

    earliest = vintage_rows[0]["date"] if isinstance(vintage_rows[0], dict) else vintage_rows[0]
    common = {
        "series_id": series_id,
        "observation_start": C.START_DATE,
        "limit": FRED_OBSERVATION_LIMIT,
    }
    initial_payloads: list[dict] = []
    initial_start = min(date.fromisoformat(vintage_start), date.today())
    initial_end = date.today()
    window_days = {
        "D": 1_800,
        "W": 365 * 20,
    }.get(frequency, (initial_end - initial_start).days)
    cursor = initial_start
    while cursor <= initial_end:
        window_end = min(cursor + timedelta(days=window_days), initial_end)
        payload = retry(
            lambda left=cursor, right=window_end: _fred_api_json(
                fred,
                "series/observations",
                **common,
                output_type=4,
                realtime_start=left.isoformat(),
                realtime_end=right.isoformat(),
            ),
            label=f"FRED initial releases:{series_id} {cursor}~{window_end}",
        )
        if payload is None:
            return None
        initial_payloads.append(payload)
        cursor = window_end + timedelta(days=1)
    snapshot_payload: dict = {"observations": []}
    if include_earliest_snapshot:
        fetched_snapshot = retry(
            lambda: _fred_api_json(
                fred,
                "series/observations",
                **common,
                output_type=1,
                realtime_start=earliest,
                realtime_end=earliest,
            ),
            label=f"FRED earliest snapshot:{series_id}",
        )
        if fetched_snapshot is None:
            return None
        snapshot_payload = fetched_snapshot
    initial_rows = [row for payload in initial_payloads for row in payload.get("observations", [])]
    snapshot_rows = snapshot_payload.get("observations", [])
    if any(len(payload.get("observations", [])) >= FRED_OBSERVATION_LIMIT for payload in initial_payloads) or len(
        snapshot_rows
    ) >= FRED_OBSERVATION_LIMIT:
        log("fail", f"FRED:{series_id} 初次发布响应达到 API 行数上限，拒绝使用可能截断的数据")
        return None
    raw = pd.DataFrame([*snapshot_rows, *initial_rows])
    if raw.empty:
        return None
    frame = raw[["date", "realtime_start", "value"]].copy()
    frame["observation_date"] = pd.to_datetime(frame.pop("date")).dt.normalize()
    frame["available_date"] = pd.to_datetime(frame.pop("realtime_start")).dt.normalize()
    frame[col] = pd.to_numeric(frame.pop("value"), errors="coerce")
    frame = (
        frame.dropna(subset=["observation_date", "available_date", col])
        .loc[lambda value: value["observation_date"] >= pd.Timestamp(C.START_DATE)]
        .sort_values(["observation_date", "available_date"])
        .drop_duplicates("observation_date", keep="first")
        .set_index("observation_date")
    )
    frame.index.name = "observation_date"
    return frame


def _upsert_first_releases(path, new: pd.DataFrame) -> int:
    if path.exists():
        old = pd.read_csv(
            path,
            parse_dates=["observation_date", "available_date"],
            index_col="observation_date",
        )
        merged = new.combine_first(old)
    else:
        merged = new
    merged = merged[~merged.index.duplicated(keep="first")].sort_index()
    merged = merged.loc[pd.Timestamp(C.START_DATE):]
    write_csv(path, merged, index_label="observation_date")
    return len(merged)


def fetch_all(*, start: str = C.START_DATE, only: list[str] | None = None) -> dict[str, int]:
    """抓取 config.FRED_SERIES 中全部（或指定）序列并增量写盘。

    Args:
        start: 起始日期。
        only:  仅抓取指定的 FRED 序列 ID 列表；None 表示全部。

    Returns:
        {字段名: 落盘总行数}
    """
    fred = _client()
    if fred is None:
        return {}

    C.ensure_dirs()
    targets = only or list(C.FRED_SERIES.keys())
    result: dict[str, int] = {}

    log("info", f"FRED: 开始抓取 {len(targets)} 个序列 (start={start})")

    for sid in targets:
        meta = C.FRED_SERIES.get(sid)
        if meta is None:
            log("warn", f"FRED:{sid} 未在 config.FRED_SERIES 登记，跳过")
            continue
        col, desc, unit, freq = meta

        raw = retry(
            lambda s=sid: fred.get_series(s, observation_start=start),
            label=f"FRED:{sid}",
        )
        df = to_single_col(raw, col)
        if df is None:
            log("fail", f"FRED:{sid} ({desc}) 无数据")
            continue

        old = read_series_csv(C.RAW_FRED / f"{col}.csv")
        latest = df.combine_first(old) if old is not None else df
        release_path = C.RAW_FRED_RELEASES / f"{col}.csv"
        vintage_start = C.START_DATE
        include_earliest_snapshot = True
        if release_path.exists():
            existing_dates = pd.read_csv(release_path, usecols=["available_date"], parse_dates=["available_date"])
            if not existing_dates.empty:
                last_available = existing_dates["available_date"].max()
                vintage_start = (last_available - pd.Timedelta(days=31)).date().isoformat()
                include_earliest_snapshot = False
        releases = _first_releases(
            fred,
            sid,
            col,
            frequency=freq,
            latest=latest,
            vintage_start=vintage_start,
            include_earliest_snapshot=include_earliest_snapshot,
        )
        if releases is None:
            log("fail", f"FRED:{sid} ({desc}) vintage 抓取失败")
            continue

        total, added = upsert_csv(C.RAW_FRED / f"{col}.csv", df)
        result[col] = total
        if releases.empty:
            log("ok", f"FRED:{sid:<14} {desc:<22} {total:>6} 行 (+{added}), observation-only  [{unit}, {freq}]")
            continue
        release_total = _upsert_first_releases(release_path, releases)
        log(
            "ok",
            f"FRED:{sid:<14} {desc:<22} {total:>6} 行 (+{added}), vintage {release_total:>6} 行  [{unit}, {freq}]",
        )

    log("info", f"FRED: 完成 {len(result)}/{len(targets)}")
    return result


if __name__ == "__main__":
    fetch_all()
