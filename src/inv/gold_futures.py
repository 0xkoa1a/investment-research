"""Review cached COMEX quotes without asserting a vendor roll or settlement rule."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from inv import config as C
from inv.fetch_market import _download
from inv.gold_data import utc_now

NY = ZoneInfo('America/New_York')


def completed_prices(frame: pd.DataFrame, cutoff: datetime) -> pd.DataFrame:
    """Use only prior NY calendar dates; this is a conservative filter, not a close timestamp."""
    required = {'date', 'open', 'high', 'low', 'close', 'volume'}
    if required - set(frame):
        raise ValueError('行情缺少 OHLCV 字段')
    out = frame.copy()
    dates = pd.to_datetime(out['date'], format='%Y-%m-%d', errors='raise')
    if dates.duplicated().any():
        raise ValueError('行情日期重复')
    for field in ('open', 'high', 'low', 'close', 'volume'):
        out[field] = pd.to_numeric(out[field], errors='raise')
        if np.isinf(out[field]).any():
            raise ValueError('行情包含无穷值')
    if (out[['open', 'high', 'low', 'close']] <= 0).any().any() or (out.volume < 0).any():
        raise ValueError('价格或成交量非法')
    full = out[['open', 'high', 'low', 'close']].notna().all(axis=1)
    if ((out.high < out[['open', 'close', 'low']].max(axis=1)) & full).any() or (
        (out.low > out[['open', 'close', 'high']].min(axis=1)) & full
    ).any():
        raise ValueError('OHLC 高低关系不一致')
    out['date'] = dates.dt.strftime('%Y-%m-%d')
    out['known_by_boundary'] = [datetime.combine(d.date() + timedelta(days=1), time(), NY).isoformat() for d in dates]
    keep = dates.dt.date < cutoff.astimezone(NY).date()
    return out.loc[keep].sort_values('date').reset_index(drop=True)


def review_futures(cutoff: datetime, *, refresh: bool = False) -> Path:
    cache = C.ROOT / '.cache/gold-outlook/comex'
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / 'snapshots' / cutoff.strftime('%Y%m%dT%H%M%SZ')
    if target.exists():
        raise ValueError('期货核验快照已存在，拒绝覆盖')
    frames, sources = {}, {}
    for name, ticker in C.GOLD_RESEARCH_FUTURES.items():
        path = cache / f'{name}.csv'
        if refresh:
            frame = _download(ticker, '2023-08-01' if name == 'gold' else '2026-07-01')
            if frame is None:
                raise ValueError(f'{ticker} 下载失败；未创建快照')
            frame.to_csv(path)
            (cache / f'{name}-retrieval.json').write_text(json.dumps({'retrieved_at': utc_now()}))
        raw = pd.read_csv(path)
        frames[name] = completed_prices(raw, cutoff)
        stamp = cache / f'{name}-retrieval.json'
        if not stamp.exists() and name == 'gold':
            stamp = cache / 'retrieval.json'
        sources[name] = {'ticker': ticker, 'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'retrieved_at': json.loads(stamp.read_text())['retrieved_at'] if stamp.exists() else None,
                         'cache_written_at': datetime.fromtimestamp(path.stat().st_mtime, NY).isoformat(),
                         'raw_rows': len(raw), 'excluded_rows': len(raw) - len(frames[name])}
    primary = frames['gold']
    old = pd.read_csv(C.RAW_MARKET / 'gold.csv')
    overlap = primary.merge(old[['date', 'close']], on='date', suffixes=('_new', '_old'))
    changed = overlap.loc[(overlap.close_new - overlap.close_old).abs() > 0.05]
    focus = primary.loc[primary.date >= '2026-08-01']
    audit = {'report': 'gold-outlook', 'phase': 0, 'cutoff_at': cutoff.isoformat(), 'created_at': utc_now(),
             'research_instrument': 'COMEX gold futures', 'selected_primary': 'GC=F',
             'primary_price_status': 'downloaded_pending_roll_and_close_validation',
             'phase_1_authorized': False, 'sources': sources,
             'coverage': {k: {'rows': len(f), 'first': f.date.min(), 'last': f.date.max(),
                              'missing_close': int(f.close.isna().sum())} for k, f in frames.items()},
             'focus_rows': len(focus), 'focus_zero_volume_dates': focus.loc[focus.volume == 0, 'date'].tolist(),
             'changed_close_dates_vs_old': changed.date.tolist(),
             'completion_filter': 'observation date before cutoff NY calendar date; not a verified close time',
             'roll_policy': 'Yahoo historical contract mapping and adjustment rules unconfirmed',
             'public_numeric_redistribution': 'pending; price files kept in ignored local cache'}
    target.mkdir(parents=True)
    for name, f in frames.items():
        f.to_csv(target / f'{name}.csv', index=False)
    audit['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in target.glob('*.csv')}
    (target / 'manifest.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    public = C.GOLD_RESEARCH_RAW / 'reviews' / f'comex-{cutoff.strftime("%Y%m%dT%H%M%SZ")}.json'
    public.parent.mkdir(parents=True, exist_ok=True)
    if public.exists():
        raise ValueError('公开核验记录已存在')
    public.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    return public
