"""Offline descriptive gold statistics; no price filling or causal inference."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from inv import config as C
from inv.gold_data import verify_snapshot

SNAPSHOT_ID = '20260909T125258Z'
BASELINE = '2026-07-31'
AS_OF = '2026-09-08'
STAGES = (
    ('快速回升', BASELINE, '2026-08-07'),
    ('高位反复', '2026-08-07', '2026-08-18'),
    ('再度上行', '2026-08-18', '2026-08-24'),
    ('回落与反复', '2026-08-24', AS_OF),
)


def checked_series(series: pd.Series) -> pd.Series:
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError('价格索引必须为日期')
    if series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise ValueError('日期必须唯一且递增')
    if len(series) == 0 or not np.isfinite(series.to_numpy(dtype=float)).all() or (series <= 0).any():
        raise ValueError('计算窗口存在缺失、无穷或非正价格')
    return series.astype(float)


def drawdown(series: pd.Series) -> pd.Series:
    series = checked_series(series)
    return (series / series.cummax() - 1) * 100


def interval_stats(series: pd.Series, start: str, end: str) -> dict:
    series = checked_series(series)
    if pd.Timestamp(start) not in series.index or pd.Timestamp(end) not in series.index or pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError('起止必须是实际观测日期且顺序正确')
    window = series.loc[start:end]
    dd = drawdown(window)
    trough = dd.idxmin()
    peak = window.loc[:trough].idxmax()
    return {'start': start, 'end': end, 'start_close': float(window.iloc[0]),
            'end_close': float(window.iloc[-1]), 'change_pct': float((window.iloc[-1]/window.iloc[0]-1)*100),
            'intervals': len(window)-1, 'calendar_days': (window.index[-1]-window.index[0]).days,
            'max_drawdown_pct': float(dd.min()),
            'drawdown_peak': peak.isoformat() if series.index.tz else peak.date().isoformat(),
            'drawdown_trough': trough.isoformat() if series.index.tz else trough.date().isoformat()}


def intraday_results(prices: pd.Series, provenance: dict) -> dict:
    prices = checked_series(prices).tz_convert('America/New_York')
    boundaries = [BASELINE, '2026-08-07', '2026-08-18', '2026-08-25', AS_OF]
    ends = [pd.Timestamp(f'{date} 17:00', tz='America/New_York').isoformat() for date in boundaries]
    stages = [{'label': label, **interval_stats(prices, start, end)} for label, start, end in
              zip(['快速回升', '高位反复', '再度上行', '回落与反复'], ends[:-1], ends[1:], strict=True)]
    focus = prices.loc[ends[0]:ends[-1]]
    overall = interval_stats(prices, ends[0], ends[-1])
    return {'report': 'gold-outlook', 'phase': 1, 'data_as_of': AS_OF, 'inputs': provenance,
            'basis': 'GCZ26.CMX observed five-minute Close; 17:00 New York endpoints; not settlement or total investment return',
            'overall': overall, 'stages': stages, 'observed_bars': len(focus),
            'peak_bar_end': focus.idxmax().isoformat(), 'peak_close': float(focus.max()),
            'peak_to_last_pct': float((focus.iloc[-1] / focus.max() - 1) * 100)}


def load_inputs(root: Path = C.ROOT) -> tuple[dict[str, pd.Series], dict]:
    review = root / 'data/raw/gold-outlook/reviews' / f'comex-{SNAPSHOT_ID}.json'
    approved = json.loads(review.read_text())
    path = root / '.cache/gold-outlook/comex/snapshots' / SNAPSHOT_ID
    manifest = verify_snapshot(path)
    if manifest['files'] != approved['files']:
        raise ValueError('行情快照与已选择的公开哈希记录不一致')
    frames = {}
    for name in ('gold', 'gcv26', 'gcz26'):
        frame = pd.read_csv(path / f'{name}.csv', parse_dates=['date']).set_index('date')
        series = checked_series(frame.close)
        if series.index[-1] != pd.Timestamp(AS_OF):
            raise ValueError('行情截止日发生变化；需要显式更新研究版本')
        frames[name] = series
    return frames, {'snapshot': SNAPSHOT_ID, 'files': manifest['files'],
                    'review_sha256': hashlib.sha256(review.read_bytes()).hexdigest()}


def results(frames: dict[str, pd.Series], provenance: dict) -> dict:
    primary = frames['gold']
    focus = primary.loc[BASELINE:AS_OF]
    stages = [{'label': label, **interval_stats(primary, start, end)} for label, start, end in STAGES]
    return {'report': 'gold-outlook', 'phase': 1, 'data_as_of': AS_OF, 'inputs': provenance,
            'basis': 'Yahoo daily Close; descriptive series changes, not roll-adjusted investment returns',
            'overall': interval_stats(primary, BASELINE, AS_OF),
            'background': interval_stats(primary, primary.index[0].date().isoformat(), AS_OF),
            'peak_date': focus.idxmax().date().isoformat(), 'peak_close': float(focus.max()),
            'peak_change_from_baseline_pct': float((focus.max()/focus.iloc[0]-1)*100),
            'peak_to_last_pct': float((focus.iloc[-1]/focus.max()-1)*100),
            'gain_retraced_pct': float((focus.max()-focus.iloc[-1])/(focus.max()-focus.iloc[0])*100),
            'stages': stages,
            'contracts': {name: interval_stats(series, BASELINE, AS_OF) for name, series in frames.items()}}
