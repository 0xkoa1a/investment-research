"""Explicit Yahoo intraday retrieval and immutable local snapshots for gold Phase 1."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from inv import config as C
from inv.gold_data import utc_now, verify_snapshot

NY = 'America/New_York'
BAR = pd.Timedelta(minutes=5)
FIELDS = ['open', 'high', 'low', 'close', 'volume']


def aware(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None or pd.isna(stamp):
        raise ValueError('日内时间必须包含时区')
    return stamp.tz_convert('UTC')


def regular_session(index: pd.DatetimeIndex) -> np.ndarray:
    """Ordinary GC hours only. Holiday exceptions must be reviewed separately."""
    local = index.tz_convert(NY)
    return ((local.dayofweek < 5) & (local.hour != 17) &
            ~((local.dayofweek == 4) & (local.hour >= 17))) | ((local.dayofweek == 6) & (local.hour >= 18))


def normalize_bars(raw: pd.DataFrame, *, cutoff, start, end) -> tuple[pd.DataFrame, dict]:
    """Treat vendor timestamps as bar starts; retain only completed, valid observations."""
    out = raw.rename(columns=str.lower).copy()
    if 'datetime' not in out or set(FIELDS) - set(out):
        raise ValueError('日内行情缺少 Datetime / OHLCV')
    index = pd.DatetimeIndex([aware(t) for t in out.datetime])
    if index.empty or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError('日内时间必须非空、唯一且递增')
    if (index != index.floor('5min')).any():
        raise ValueError('日内标签未对齐五分钟网格')
    lower, upper = aware(start), min(aware(end), aware(cutoff))
    if lower >= upper:
        raise ValueError('日内起止时间顺序错误')
    out = out[FIELDS].apply(pd.to_numeric, errors='raise').set_axis(index)
    if np.isinf(out.to_numpy()).any():
        raise ValueError('日内行情包含无穷值')
    if (out[['open', 'high', 'low', 'close']] <= 0).any().any() or (out.volume < 0).any():
        raise ValueError('日内价格或成交量非法')
    valid = out.notna().all(axis=1).to_numpy()
    if ((out.high < out[['open', 'close', 'low']].max(axis=1)) & valid).any() or (
        (out.low > out[['open', 'close', 'high']].min(axis=1)) & valid
    ).any():
        raise ValueError('日内 OHLC 高低关系不一致')
    in_window = (index >= lower) & (index + BAR <= upper)
    in_session = regular_session(index)
    excluded = []
    for pos in np.flatnonzero(~(valid & in_window & in_session)):
        reasons = [label for mask, label in [(valid, 'missing_ohlcv'), (in_window, 'outside_completed_window'),
                                             (in_session, 'outside_regular_gc_hours')] if not mask[pos]]
        excluded.append({'bar_start': index[pos].isoformat(), 'reasons': reasons})
    out = out.loc[valid & in_window & in_session].copy()
    if out.empty:
        raise ValueError('没有完整可用的日内柱')
    grid = pd.date_range(lower.ceil('5min'), upper - BAR, freq='5min')
    absent = grid[regular_session(grid)].difference(out.index)
    # Do not interpolate or silently classify holiday absences as exchange closures.
    gaps = [{'previous_bar_end': (left + BAR).isoformat(), 'next_bar_start': right.isoformat(),
             'elapsed_minutes': int((right - left) / pd.Timedelta(minutes=1))}
            for left, right in zip(out.index[:-1], out.index[1:], strict=True) if right - left > BAR]
    audit = {'raw_rows': len(raw), 'retained_rows': len(out), 'excluded': excluded,
             'first_bar_start': out.index[0].isoformat(), 'last_bar_end': (out.index[-1] + BAR).isoformat(),
             'zero_volume_rows': int((out.volume == 0).sum()),
             'absent_on_regular_session_grid': [t.isoformat() for t in absent],
             'grid_note': 'Ordinary hours only; absences around holidays are not a verified missing-trade count.',
             'gaps': gaps, 'fill_policy': 'none; chart breaks at every gap longer than five minutes'}
    out.insert(0, 'bar_end', out.index + BAR)
    out.index.name = 'bar_start'
    return out.reset_index(), audit


def freeze_intraday(cutoff: datetime, *, refresh: bool = False) -> Path:
    spec = C.GOLD_RESEARCH_INTRADAY
    cache = C.ROOT / '.cache/gold-outlook/intraday'
    snapshot_id = aware(cutoff).strftime('%Y%m%dT%H%M%SZ')
    target = cache / 'snapshots' / snapshot_id
    public = C.GOLD_RESEARCH_RAW / 'reviews' / f'intraday-{snapshot_id}.json'
    if target.exists() or public.exists():
        raise ValueError('日内快照已存在，拒绝覆盖')
    downloads = cache / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    frames, raw_files, sources = {}, {}, {}
    for name, ticker in C.GOLD_RESEARCH_FUTURES.items():
        path, meta_path = downloads / f'{name}.csv', downloads / f'{name}-retrieval.json'
        request = {'ticker': ticker, 'interval': spec['interval'], 'start': spec['start'], 'end': spec['end'],
                   'auto_adjust': False, 'actions': False, 'prepost': True, 'keepna': True}
        if refresh:
            import yfinance as yf
            instrument = yf.Ticker(ticker)
            data = instrument.history(start=aware(spec['start']).to_pydatetime(), end=aware(spec['end']).to_pydatetime(),
                                      interval=spec['interval'], auto_adjust=False, actions=False,
                                      prepost=True, keepna=True, timeout=30)
            if data.empty:
                raise ValueError(f'{ticker} 返回空行情；未建立快照')
            metadata = instrument.get_history_metadata()
            data.to_csv(path, index_label='Datetime')
            meta_path.write_text(json.dumps({'request': request, 'retrieved_at': utc_now(),
                'yfinance_version': yf.__version__, 'vendor_metadata': {k: metadata.get(k) for k in
                    ['symbol', 'currency', 'exchangeName', 'instrumentType', 'exchangeTimezoneName', 'dataGranularity']}},
                ensure_ascii=False, indent=2) + '\n')
        meta = json.loads(meta_path.read_text())
        if meta['request'] != request:
            raise ValueError('缓存请求范围与配置不同；需要 --refresh')
        vendor = meta['vendor_metadata']
        if vendor['symbol'] != ticker or vendor['currency'] != 'USD' or vendor['instrumentType'] != 'FUTURE' or vendor['dataGranularity'] != '5m':
            raise ValueError('Yahoo 品种或频率元数据不符')
        frames[name], quality = normalize_bars(pd.read_csv(path), cutoff=cutoff, start=spec['start'], end=spec['end'])
        sources[name] = {**meta, 'quality': quality}
        raw_files[name] = path.read_bytes()
    manifest = {'report': 'gold-outlook', 'phase': 1, 'cutoff_at': aware(cutoff).isoformat(), 'created_at': utc_now(),
                'sample_start': spec['start'], 'sample_end': spec['end'], 'interval': spec['interval'],
                'primary': spec['primary'], 'unit': spec['unit'], 'sources': sources,
                'timestamp_convention': 'Yahoo five-minute labels treated as interval starts; plot at label + five minutes in New York time. Not exchange settlement.',
                'gc_equals_december_ohlcv': frames['gold'].equals(frames['gcz26']),
                'redistribution': 'unconfirmed; full raw data and Plotly files remain in ignored local storage'}
    target.mkdir(parents=True)
    for name, frame in frames.items():
        frame.to_csv(target / f'{name}.csv', index=False)
        (target / f'{name}-raw.csv').write_bytes(raw_files[name])
    manifest['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.iterdir())}
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    (target / 'manifest.json').write_text(payload)
    public.parent.mkdir(parents=True, exist_ok=True)
    public.write_text(payload)
    return public


def load_intraday(root: Path = C.ROOT) -> tuple[pd.Series, dict]:
    selection_path = root / 'data/raw/gold-outlook/phase1/intraday-input.json'
    selection = json.loads(selection_path.read_text())
    snapshot_id = selection['snapshot']
    if not isinstance(snapshot_id, str) or not pd.Series([snapshot_id]).str.fullmatch(r'\d{8}T\d{6}Z').all():
        raise ValueError('非法的日内快照标识')
    path = root / '.cache/gold-outlook/intraday/snapshots' / snapshot_id
    public = root / 'data/raw/gold-outlook/reviews' / f'intraday-{snapshot_id}.json'
    manifest = verify_snapshot(path)
    if manifest != json.loads(public.read_text()) or selection['primary'] != manifest['primary']:
        raise ValueError('日内快照与公开核验记录不一致')
    if manifest['sample_end'] != C.GOLD_RESEARCH_INTRADAY['end']:
        raise ValueError('日内样本截止发生变化，需要显式修订研究')
    frame = pd.read_csv(path / f'{manifest["primary"]}.csv')
    prices = pd.Series(frame.close.to_numpy(), index=pd.to_datetime(frame.bar_end, utc=True), name='GCZ26.CMX')
    return prices, {'snapshot': snapshot_id, 'files': manifest['files'], 'primary': manifest['primary'],
                    'selection_sha256': hashlib.sha256(selection_path.read_bytes()).hexdigest(),
                    'review_sha256': hashlib.sha256(public.read_bytes()).hexdigest()}


def broken_line(prices: pd.Series) -> tuple[list, list]:
    """Insert a null between disjoint observations, including maintenance/weekend gaps."""
    x, y = [], []
    previous = None
    for stamp, price in prices.items():
        local = stamp.tz_convert(NY).tz_localize(None).isoformat()
        if previous is not None and stamp - previous > BAR:
            x.append((previous + BAR).tz_convert(NY).tz_localize(None).isoformat())
            y.append(None)
        x.append(local)
        y.append(float(price))
        previous = stamp
    return x, y
