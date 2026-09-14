"""Gold Phase 0: dated inputs, explicit availability and immutable public snapshots.

No price attribution or return analysis is performed here. Restricted vendor
tables are not copied into public snapshots. FRED vintages use the last complete
Chicago calendar day, rather than silently importing later same-day revisions.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from inv import config as C

BACKGROUND_START = "2023-08-01"
FOCUS_START = "2026-08-01"
CHICAGO = ZoneInfo("America/Chicago")
NORMAL_COLUMNS = ["observation_date", "value", "available_at", "known_by_at", "vintage_date"]


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("截止时间必须包含时区")
    return parsed.astimezone(timezone.utc)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def completed_vintage(cutoff: datetime) -> tuple[str, str]:
    day = cutoff.astimezone(CHICAGO).date()
    known_by = datetime.combine(day, datetime.min.time(), CHICAGO)
    return (day - timedelta(days=1)).isoformat(), known_by.astimezone(timezone.utc).isoformat()


def catalog() -> dict[str, dict]:
    result = {}
    for sid in C.GOLD_RESEARCH_FRED_IDS:
        col, description, unit, frequency = C.FRED_SERIES[sid]
        result[col] = {
            "provider": "FRED/ALFRED", "source_id": sid, "description": description,
            "unit": unit, "frequency": frequency, "timezone": "America/Chicago (vintage dates)",
            "source_url": f"https://fred.stlouisfed.org/series/{sid}", "public_data": True,
            "rights_url": "https://fred.stlouisfed.org/legal/terms/",
            "revision_policy": "截至指定 vintage 的修订值；known_by_at 是可知上界，不是首次发布时间",
        }
    for col, (description, unit, frequency, url) in C.GOLD_RESEARCH_CANDIDATES.items():
        result[col] = {
            "provider": "candidate", "source_id": col, "description": description,
            "unit": unit, "frequency": frequency, "timezone": "待核验",
            "source_url": url, "public_data": False, "rights_url": "",
            "revision_policy": "待核验；不得推定未取得的数据或公开许可",
        }
    result["cot_gold"] = {
        "provider": "CFTC", "source_id": "088691", "description": "COMEX Gold, Disaggregated Futures Only",
        "unit": "contracts", "frequency": "W", "timezone": "America/New_York (release)",
        "source_url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm",
        "public_data": True, "rights_url": "https://www.cftc.gov/WebPolicy/index.htm",
        "revision_policy": "下载时的年度档案；不代表每周初次发布版本；未核验的公布时间留空",
    }
    return result


def download(url: str, *, params: dict | None = None) -> bytes:
    """Never expose an authenticated request URL or server error body in logs."""
    reason = "unknown"
    for attempt in range(2):
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.ok:
                return response.content
            reason = f"HTTP {response.status_code}"
            if response.status_code in {401, 403, 404, 429}:
                break
        except requests.RequestException as error:
            reason = type(error).__name__
        if attempt == 0:
            time.sleep(1)
    raise RuntimeError(f"下载失败：{reason}") from None


def validate_observations(frame: pd.DataFrame, cutoff: datetime, *, price: bool = False) -> pd.DataFrame:
    """Reject duplicate/invalid rows; retain missing values and never interpolate."""
    if set(NORMAL_COLUMNS) - set(frame.columns):
        raise ValueError("观测文件缺少日期、值、可用时间或 vintage 字段")
    out = frame.copy()
    dates = out["observation_date"].astype(str)
    if not dates.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise ValueError("observation_date 必须为 YYYY-MM-DD")
    parsed = pd.to_datetime(dates, errors="raise")
    if parsed.duplicated().any():
        raise ValueError("观测日期重复；必须先解决来源冲突")
    out["value"] = pd.to_numeric(out["value"], errors="raise")
    if np.isinf(out["value"]).any():
        raise ValueError("观测值不能为无穷大")
    if price and (out["value"].dropna() <= 0).any():
        raise ValueError("黄金价格必须为正数")
    keep = (parsed >= pd.Timestamp(BACKGROUND_START)) & (parsed.dt.date <= cutoff.date())
    for field in ("available_at", "known_by_at"):
        values = out[field].fillna("").astype(str)
        for index, value in values.items():
            if value and timestamp(value) > cutoff:
                keep.loc[index] = False
    if price:
        if "session_close_at" not in out or out["session_close_at"].fillna("").eq("").any():
            raise ValueError("价格必须提供带时区的 session_close_at 以排除未完成交易日")
        for index, value in out["session_close_at"].items():
            if timestamp(str(value)) > cutoff:
                keep.loc[index] = False
    return out.loc[keep].sort_values("observation_date").reset_index(drop=True)


def fred_snapshot(series_id: str, cutoff: datetime, cache: Path, *, refresh: bool) -> tuple[pd.DataFrame, dict]:
    vintage, known_by = completed_vintage(cutoff)
    path = cache / f"{series_id}-{vintage}.json"
    if refresh:
        key = C.fred_api_key()
        if not key:
            raise RuntimeError("FRED_API_KEY 未配置")
        payload = json.loads(download("https://api.stlouisfed.org/fred/series/observations", params={
            "api_key": key, "file_type": "json", "series_id": series_id,
            "observation_start": BACKGROUND_START, "observation_end": cutoff.date().isoformat(),
            "realtime_start": vintage, "realtime_end": vintage, "limit": 100_000,
        }))
        if int(payload.get("count", 0)) != len(payload.get("observations", [])):
            raise ValueError("FRED 返回分页不完整")
        if not payload.get("observations"):
            raise ValueError("FRED 返回空序列")
        bundle = {"retrieved_at": utc_now(), "payload": payload}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(bundle), encoding="utf-8")
    else:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    rows = [{
        "observation_date": row["date"], "value": np.nan if row["value"] == "." else float(row["value"]),
        "available_at": "", "known_by_at": known_by, "vintage_date": vintage,
    } for row in bundle["payload"]["observations"]]
    frame = validate_observations(pd.DataFrame(rows), cutoff)
    return frame, {"retrieved_at": bundle["retrieved_at"], "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def cftc_snapshot(cutoff: datetime, cache: Path, releases: dict[str, str], *, refresh: bool) -> tuple[pd.DataFrame, dict]:
    frames, provenance = [], []
    for year in range(2023, cutoff.year + 1):
        path = cache / f"cftc-{year}.zip"
        meta_path = cache / f"cftc-{year}.json"
        url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
        if refresh:
            data = download(url)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if len(archive.namelist()) != 1:
                    raise ValueError("CFTC 压缩包结构不符合预期")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            meta_path.write_text(json.dumps({"retrieved_at": utc_now(), "url": url}), encoding="utf-8")
        with zipfile.ZipFile(path) as archive:
            with archive.open(archive.namelist()[0]) as handle:
                frame = pd.read_csv(handle, dtype={"CFTC_Contract_Market_Code": str}, low_memory=False)
        selected = frame.loc[frame["CFTC_Contract_Market_Code"].str.strip().eq("088691")].copy()
        if selected.empty or not selected["Market_and_Exchange_Names"].str.strip().eq("GOLD - COMMODITY EXCHANGE INC.").all():
            raise ValueError("CFTC Gold 合约身份校验失败")
        frames.append(pd.DataFrame({
            "observation_date": pd.to_datetime(selected["Report_Date_as_YYYY-MM-DD"]).dt.strftime("%Y-%m-%d"),
            "value": selected["M_Money_Positions_Long_All"] - selected["M_Money_Positions_Short_All"],
            "managed_money_long": selected["M_Money_Positions_Long_All"],
            "managed_money_short": selected["M_Money_Positions_Short_All"],
            "managed_money_spreading": selected["M_Money_Positions_Spread_All"],
            "open_interest": selected["Open_Interest_All"],
        }))
        provenance.append({**json.loads(meta_path.read_text()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    data = pd.concat(frames, ignore_index=True)
    data["available_at"] = data["observation_date"].map(releases).fillna("")
    data["known_by_at"] = ""
    data["vintage_date"] = ""
    # Exclude recent rows unless their actual release is confirmed. Older rows
    # remain descriptive only: the downloaded archive may contain revisions.
    data = data.loc[(data["observation_date"] < FOCUS_START) | data["available_at"].ne("")]
    return validate_observations(data, cutoff), {"retrieved_at": max(p["retrieved_at"] for p in provenance), "inputs": provenance}


def build_snapshot(cutoff: datetime, *, refresh: bool = False, root: Path = C.GOLD_RESEARCH_RAW,
                   cache: Path = C.ROOT / ".cache/gold-outlook/downloads", imports: Path | None = None) -> Path:
    if cutoff > datetime.now(timezone.utc):
        raise ValueError("研究截止时间不能位于未来")
    snapshot_id = cutoff.strftime("%Y%m%dT%H%M%SZ")
    target = root / "snapshots" / snapshot_id
    if target.exists():
        raise ValueError("该截止时间的快照已存在；不得覆盖，请使用新的截止时间")
    reviews_path = root / "source-review.json"
    review = json.loads(reviews_path.read_text(encoding="utf-8")) if reviews_path.exists() else {}
    releases = review.get("cftc_release_times", {})
    sources = catalog()
    frames, records = {}, {}

    def fetch(sid: str) -> tuple[str, pd.DataFrame | None, dict]:
        col = C.FRED_SERIES[sid][0]
        try:
            data, meta = fred_snapshot(sid, cutoff, cache, refresh=refresh)
            return col, data, {"status": "downloaded", **meta}
        except (RuntimeError, ValueError, OSError) as error:
            # Exception messages here never contain a request URL or API key.
            return col, None, {"status": "failed", "error": type(error).__name__}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for col, data, meta in pool.map(fetch, C.GOLD_RESEARCH_FRED_IDS):
            records[col] = meta
            if data is not None:
                frames[col] = data
    try:
        frames["cot_gold"], meta = cftc_snapshot(cutoff, cache, releases, refresh=refresh)
        records["cot_gold"] = {"status": "downloaded", **meta}
    except (RuntimeError, ValueError, OSError, zipfile.BadZipFile) as error:
        records["cot_gold"] = {"status": "failed", "error": type(error).__name__}

    if imports:
        for path in sorted(imports.glob("*.csv")):
            col = path.stem
            if col not in sources:
                raise ValueError(f"未登记的导入字段：{col}")
            if not sources[col]["public_data"]:
                raise ValueError(f"{col} 未确认公开保存权限；不能导入公共快照")
            if col in frames:
                raise ValueError(f"{col} 已从来源取得，拒绝静默覆盖")
            frames[col] = validate_observations(pd.read_csv(path), cutoff, price=col in {"xauusd", "gold"})
            records[col] = {"status": "imported", "retrieved_at": utc_now(),
                            "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".gold-stage-", dir=target.parent))
    try:
        coverage = []
        for col, source in sources.items():
            observed_review = review.get("sources", {}).get(col, {})
            record = {"status": "not_downloaded", **observed_review, **records.get(col, {})}
            row = {"series": col, **source, **record, "rows": 0, "valid_rows": 0,
                   "first_observation": "", "last_observation": "", "focus_rows": 0,
                   "latest_available_at": "", "known_by_at": "", "file": "", "sha256": ""}
            if col in frames:
                data = frames[col]
                filename = f"{col}.csv"
                data.to_csv(stage / filename, index=False, lineterminator="\n")
                valid = data.loc[data["value"].notna()]
                row.update({"rows": len(data), "valid_rows": len(valid),
                            "first_observation": valid["observation_date"].min() if len(valid) else "",
                            "last_observation": valid["observation_date"].max() if len(valid) else "",
                            "focus_rows": int((valid["observation_date"] >= FOCUS_START).sum()),
                            "latest_available_at": data["available_at"].fillna("").max() if len(data) else "",
                            "known_by_at": data["known_by_at"].fillna("").max() if len(data) else "",
                            "file": filename, "sha256": hashlib.sha256((stage / filename).read_bytes()).hexdigest()})
            coverage.append(row)
        (stage / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if reviews_path.exists():
            shutil.copyfile(reviews_path, stage / "source-review.json")
        # Keep nested provenance in the manifest, compact scalar fields in CSV.
        pd.DataFrame([{k: v for k, v in row.items() if not isinstance(v, (dict, list))} for row in coverage]).to_csv(
            stage / "coverage.csv", index=False, lineterminator="\n")
        manifest = {
            "report": "gold-outlook", "phase": 0, "cutoff_at": cutoff.isoformat(), "created_at": utc_now(),
            "background_start": BACKGROUND_START, "focus_start": FOCUS_START,
            "fred_vintage_date": completed_vintage(cutoff)[0],
            "primary_price_series": C.GOLD_RESEARCH_PRIMARY,
            "primary_price_status": "pending_futures_review", "phase_1_authorized": False,
            "series": coverage,
            "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.iterdir())},
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stage.rename(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target


def verify_snapshot(path: Path) -> dict:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    if set(p.name for p in path.iterdir()) != {"manifest.json", *files}:
        raise ValueError("快照包含未声明或缺失的文件")
    for name, digest in files.items():
        if not re.fullmatch(r"[a-zA-Z0-9_-]+\.(csv|json)", name):
            raise ValueError("不安全的快照文件名")
        if hashlib.sha256((path / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"快照哈希不匹配：{name}")
    return manifest
