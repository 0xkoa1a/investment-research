"""Fetch Phase 0 FRED and CFTC series into normalized in-memory frames."""
from __future__ import annotations

import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from inv import config as C
from inv import gold_data as G


def _check_date(value: str, label: str) -> pd.Timestamp:
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} 必须是 YYYY-MM-DD') from exc
    if pd.isna(parsed) or parsed.tzinfo is not None or parsed.strftime('%Y-%m-%d') != value:
        raise ValueError(f'{label} 必须是 YYYY-MM-DD')
    return parsed


def _filter_start(frame: pd.DataFrame, start: str, cutoff: datetime) -> pd.DataFrame:
    last_date = cutoff.astimezone(G.CHICAGO).date().isoformat()
    return frame.loc[frame.observation_date.between(start, last_date)].sort_values('observation_date').reset_index(drop=True)


def _fred_one(sid: str, cutoff: datetime, background_start: str, download_dir: Path) -> tuple[str, pd.DataFrame | None, dict]:
    col = C.FRED_SERIES[sid][0]
    try:
        frame, meta = G.fred_snapshot(sid, cutoff, download_dir, refresh=True)
        frame = _filter_start(frame, background_start, cutoff)
        if frame.empty:
            raise ValueError('FRED 返回区间内无观测')
        return col, frame, {'status': 'downloaded', **meta}
    except Exception as exc:  # Per-series isolation; exception text may contain credentials or URLs.
        return col, None, {'status': 'failed', 'error_type': type(exc).__name__,
                           'message': 'FRED series unavailable or invalid'}


def _validate_cftc(frame: pd.DataFrame, background_start: str, cutoff: datetime) -> pd.DataFrame:
    required = {'observation_date', 'value', 'managed_money_long', 'managed_money_short',
                'managed_money_spreading', 'open_interest', 'available_at', 'known_by_at', 'vintage_date'}
    if required - set(frame):
        raise ValueError('CFTC 序列缺少必需字段')
    out = _filter_start(frame, background_start, cutoff)
    fields = ['value', 'managed_money_long', 'managed_money_short', 'managed_money_spreading', 'open_interest']
    out[fields] = out[fields].apply(pd.to_numeric, errors='raise')
    if np.isinf(out[fields].to_numpy(dtype=float)).any():
        raise ValueError('CFTC 持仓包含无穷值')
    if (out[['managed_money_long', 'managed_money_short', 'managed_money_spreading', 'open_interest']] < 0).any().any():
        raise ValueError('CFTC 总持仓、跨期和未平仓量不能为负')
    if not np.array_equal(out.value.to_numpy(),
                          (out.managed_money_long - out.managed_money_short).to_numpy()):
        raise ValueError('CFTC 净持仓必须等于 managed money 多头减空头')
    return out


def _read_cftc_focus(download_dir: Path, cutoff: datetime, background_start: str,
                     focus_start: str, release_times: dict[str, str]) -> pd.DataFrame:
    """Read verified downloaded annual archives, preserving background before the chosen focus."""
    required = ['CFTC_Contract_Market_Code', 'Market_and_Exchange_Names', 'Report_Date_as_YYYY-MM-DD',
                'M_Money_Positions_Long_All', 'M_Money_Positions_Short_All',
                'M_Money_Positions_Spread_All', 'Open_Interest_All']
    chunks = []
    last_date = cutoff.astimezone(G.CHICAGO).date().isoformat()
    for year in range(pd.Timestamp(background_start).year, cutoff.astimezone(G.CHICAGO).year + 1):
        archive_path = download_dir / f'cftc-{year}.zip'
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != 1:
                raise ValueError('CFTC 压缩包结构不符合预期')
            with archive.open(names[0]) as handle:
                raw = pd.read_csv(handle, dtype={'CFTC_Contract_Market_Code': str}, low_memory=False)
        missing = set(required) - set(raw)
        if missing:
            raise ValueError('CFTC 年度档案缺少字段')
        selected = raw.loc[raw.CFTC_Contract_Market_Code.str.strip().eq('088691')].copy()
        if selected.empty or not selected.Market_and_Exchange_Names.str.strip().eq(
                'GOLD - COMMODITY EXCHANGE INC.').all():
            raise ValueError('CFTC Gold 合约身份校验失败')
        selected['observation_date'] = pd.to_datetime(
            selected['Report_Date_as_YYYY-MM-DD'], errors='raise').dt.strftime('%Y-%m-%d')
        if selected.observation_date.duplicated().any():
            raise ValueError('CFTC 年度档案包含重复观测日期')
        for field in ['M_Money_Positions_Long_All', 'M_Money_Positions_Short_All',
                      'M_Money_Positions_Spread_All', 'Open_Interest_All']:
            selected[field] = pd.to_numeric(selected[field], errors='raise')
        selected = selected.loc[selected.observation_date.between(background_start, last_date)]
        recent = selected.observation_date >= focus_start
        release = selected.observation_date.map(release_times).fillna('')
        released_by_cutoff = []
        for value in release:
            if not value:
                released_by_cutoff.append(False)
                continue
            instant = pd.Timestamp(value)
            if instant.tzinfo is None:
                raise ValueError('CFTC release_times 必须带时区')
            released_by_cutoff.append(instant.tz_convert('UTC') <= pd.Timestamp(cutoff).tz_convert('UTC'))
        keep = ~recent.to_numpy() | np.asarray(released_by_cutoff)
        selected = selected.loc[keep].copy()
        selected['available_at'] = release.loc[selected.index]
        selected['known_by_at'] = ''
        selected['vintage_date'] = ''
        selected['managed_money_long'] = selected.M_Money_Positions_Long_All
        selected['managed_money_short'] = selected.M_Money_Positions_Short_All
        selected['managed_money_spreading'] = selected.M_Money_Positions_Spread_All
        selected['open_interest'] = selected.Open_Interest_All
        selected['value'] = selected.managed_money_long - selected.managed_money_short
        chunks.append(selected[['observation_date', 'value', 'managed_money_long', 'managed_money_short',
            'managed_money_spreading', 'open_interest', 'available_at', 'known_by_at', 'vintage_date']])
    if not chunks:
        raise ValueError('CFTC 年度档案没有所需年份')
    return pd.concat(chunks, ignore_index=True).sort_values('observation_date').reset_index(drop=True)


def fetch_government(cutoff: datetime, background_start: str, focus_start: str, download_dir: Path,
                     release_times: dict[str, str]) -> tuple[dict[str, pd.DataFrame], dict[str, dict]]:
    """Retrieve registered government series independently; preserve gaps and per-series failures."""
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError('cutoff 必须是带时区的 datetime')
    start = _check_date(background_start, 'background_start')
    focus = _check_date(focus_start, 'focus_start')
    earliest = pd.Timestamp(G.BACKGROUND_START)
    if start < earliest:
        raise ValueError(f'background_start 不能早于 {G.BACKGROUND_START}')
    if focus < start:
        raise ValueError('focus_start 不能早于 background_start')
    download_dir = Path(download_dir)
    ids = tuple(C.GOLD_RESEARCH_FRED_IDS)
    if any(sid not in C.FRED_SERIES for sid in ids):
        raise ValueError('GOLD_RESEARCH_FRED_IDS 含未登记的 FRED 序列')

    frames: dict[str, pd.DataFrame] = {}
    records: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for col, frame, status in pool.map(lambda sid: _fred_one(sid, cutoff, background_start, download_dir), ids):
            sid = next(s for s in ids if C.FRED_SERIES[s][0] == col)
            _, _, unit, frequency = C.FRED_SERIES[sid]
            base = {'provider': 'FRED/ALFRED', 'source_id': sid, 'unit': unit, 'frequency': frequency,
                    'timezone': 'America/Chicago (vintage dates)',
                    'source_url': f'https://fred.stlouisfed.org/series/{sid}',
                    'first_publication_unknown': True,
                    'fred_vintage_date': G.completed_vintage(cutoff)[0]}
            if frame is not None:
                frames[col] = frame
                records[col] = {**base, **status, 'missing_observations': int(frame.value.isna().sum()),
                                'focus_rows': int((frame.observation_date >= focus_start).sum())}
            else:
                records[col] = {**base, **status, 'missing_observations': None, 'focus_rows': 0}

    cftc_meta_base = {'provider': 'CFTC', 'source_id': '088691', 'unit': 'contracts', 'frequency': 'W',
                      'timezone': 'America/New_York (release)',
                      'source_url': 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm',
                      'first_publication_unknown': True, 'fred_vintage_date': None}
    try:
        _, metadata = G.cftc_snapshot(cutoff, download_dir, release_times, refresh=True)
        cftc = _read_cftc_focus(download_dir, cutoff, background_start, focus_start, release_times)
        cftc = _validate_cftc(cftc, background_start, cutoff)
        frames['cot_gold'] = cftc
        records['cot_gold'] = {**cftc_meta_base, 'status': 'downloaded', **metadata,
                               'missing_observations': int(cftc.value.isna().sum()),
                               'focus_rows': int((cftc.observation_date >= focus_start).sum())}
    except Exception as exc:  # Keep other successfully fetched series available.
        records['cot_gold'] = {**cftc_meta_base, 'status': 'failed', 'error_type': type(exc).__name__,
                               'message': 'CFTC series unavailable or invalid', 'missing_observations': None,
                               'focus_rows': 0}
    return frames, records
