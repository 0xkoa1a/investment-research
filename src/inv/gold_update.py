"""Phase 4: import a new fixed snapshot and compare it with the research baseline."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from inv import config as C
from inv.gold_analysis import BASELINE, checked_series, interval_stats
from inv.gold_data import fred_snapshot, timestamp, utc_now, verify_snapshot
from inv.gold_drivers import date_window, dated, digest, fedwatch, gld_holdings, write_json
from inv.gold_intraday import NY, normalize_bars

FRED_IDS = ('DGS2', 'DGS10', 'DFII10', 'DFII5', 'T10YIE', 'DTWEXBGS', 'DCOILWTICO',
            'DFF', 'DFEDTARL', 'DFEDTARU', 'ICSA')
PHASE = Path('data/raw/gold-outlook/phase4')


def daily_closes(prices: pd.Series) -> pd.Series:
    local = checked_series(prices).tz_convert(NY)
    result = local.loc[(local.index.hour == 17) & (local.index.minute == 0)].copy()
    result.index = result.index.tz_localize(None).normalize()
    return result


def compare_versions(old: pd.Series, new: pd.Series) -> dict:
    """Separate revised old observations from movements after the old last date."""
    for series in (old, new):
        if not isinstance(series.index, pd.DatetimeIndex) or series.index.has_duplicates or not series.index.is_monotonic_increasing:
            raise ValueError('版本比较需要唯一、递增的日期')
        if np.isinf(series.to_numpy(dtype=float)).any():
            raise ValueError('版本比较包含无穷值')
    old, new = old.dropna(), new.dropna()
    if old.empty or new.empty:
        raise ValueError('版本比较缺少有效值')
    old_date, new_date = old.index[-1], new.index[-1]
    if new_date < old_date:
        raise ValueError('新版本的有效覆盖反而缩短')
    common = old.index.intersection(new.index)
    revised = ~np.isclose(old.loc[common], new.loc[common], atol=1e-9, rtol=0)
    at_old = float(new.loc[old_date]) if old_date in new.index else None
    return {'old_date': old_date.isoformat(), 'old_value': float(old.iloc[-1]),
            'new_date': new_date.isoformat(), 'new_value': float(new.iloc[-1]),
            'status': 'new_observations' if new_date > old_date else 'no_new_observation',
            'new_value_at_old_date': at_old,
            'revision_at_old_date': None if at_old is None else at_old - float(old.iloc[-1]),
            'change_since_old_observation': None if at_old is None else float(new.iloc[-1]) - at_old,
            'change_pct_since_old_observation': None if at_old in (None, 0) else (float(new.iloc[-1]) / at_old - 1) * 100,
            'revised_overlap_dates': [d.isoformat() for d in common[revised]],
            'missing_old_dates': [d.isoformat() for d in old.index.difference(new.index)]}


def future_calendar(events: list[dict], cutoff: str) -> list[dict]:
    """Use verified release clocks; convert DST through IANA zones, never fixed offsets."""
    result, ids = [], set()
    for event in events:
        if event['id'] in ids:
            raise ValueError('日历事件ID重复')
        ids.add(event['id'])
        when = pd.Timestamp(timestamp(event['scheduled_at']))
        if when <= pd.Timestamp(timestamp(cutoff)):
            continue
        if event.get('actual') is not None:
            raise ValueError('未来事件不能填入实际发布值')
        result.append({**event, 'new_york': when.tz_convert(NY).isoformat(),
                       'beijing': when.tz_convert('Asia/Shanghai').isoformat(),
                       'within_four_weeks': when <= pd.Timestamp(cutoff) + pd.Timedelta(weeks=4)})
    return sorted(result, key=lambda e: timestamp(e['scheduled_at']))


def checked_fedwatch(path: Path) -> pd.DataFrame:
    if path.read_bytes().lstrip().lower().startswith((b'<', b'<!doctype')):
        raise ValueError('FedWatch返回HTML错误页，不能用作概率CSV')
    return fedwatch(pd.read_csv(path))


def freeze_update(cutoff: datetime, end: str, imports: Path, *, root: Path = C.ROOT) -> Path:
    """Import vendor exports and FRED vintage responses. Never refresh shared raw data."""
    sample_end = pd.Timestamp(f'{end}T17:00:00', tz=NY)
    if sample_end > pd.Timestamp(cutoff) or sample_end.dayofweek >= 5:
        raise ValueError('日终未完成或不在常规交易日；需核验交易日历')
    phase = root / PHASE
    evidence_path = phase / 'evidence.json'
    evidence = json.loads(evidence_path.read_text())
    if timestamp(evidence['information_cutoff_at']) != cutoff:
        raise ValueError('证据截止与请求不同')
    snapshot_id = cutoff.strftime('%Y%m%dT%H%M%SZ')
    public = phase / 'snapshots' / snapshot_id
    private = root / '.cache/gold-outlook/phase4/snapshots' / snapshot_id
    if public.exists() or private.exists() or (phase / 'inputs.json').exists():
        raise ValueError('更新快照或输入选择已存在，拒绝覆盖')
    frames, sources = {}, {}
    for sid in FRED_IDS:
        name = C.FRED_SERIES[sid][0]
        frame, meta = fred_snapshot(sid, cutoff, imports, refresh=False)
        frames[name] = frame
        sources[name] = {**meta, 'source_id': sid, 'url': f'https://fred.stlouisfed.org/series/{sid}',
                         'unit': C.FRED_SERIES[sid][2], 'frequency': 'W' if sid == 'ICSA' else 'D',
                         'timezone': 'observation date only', 'available_at': None,
                         'known_by_at': frame.known_by_at.iloc[0], 'vintage_date': frame.vintage_date.iloc[0],
                         'revision_status': 'fixed FRED vintage; not first-release vintage'}
    meta = json.loads((imports / 'gold-retrieval.json').read_text())
    vendor = meta['vendor']
    if any(vendor[k] != expected for k, expected in {
        'symbol': 'GCZ26.CMX', 'currency': 'USD', 'instrumentType': 'FUTURE', 'dataGranularity': '5m'}.items()):
        raise ValueError('黄金品种或频率元数据不符')
    gold, audit = normalize_bars(pd.read_csv(imports / 'gold-raw.csv'), cutoff=cutoff,
                               start=f'{BASELINE}T16:55:00-04:00', end=sample_end)
    if pd.Timestamp(gold.bar_end.iloc[-1]) != sample_end:
        raise ValueError('缺少指定日终价格，不回退到较早价格')
    commercial = {'gold': gold}
    sources['gold'] = {**meta, 'url': 'https://finance.yahoo.com/quote/GCZ26.CMX/history/',
                       'raw_sha256': digest(imports / 'gold-raw.csv'), 'unit': 'USD/troy oz', 'frequency': '5min',
                       'timezone': NY, 'available_at': None, 'revision_status': 'historical download',
                       'clock': 'bar end = vendor label + 5 minutes; 17:00 endpoint is not settlement', 'quality': audit}
    for name, ticker in C.GOLD_RESEARCH_DRIVER_MARKETS.items():
        path = imports / f'{name}-raw.csv'
        raw = pd.read_csv(path)
        dates = pd.to_datetime(raw['date'], utc=True).dt.tz_convert(NY)
        if not (dates.dt.hour.eq(0) & dates.dt.minute.eq(0)).all():
            raise ValueError('Yahoo日度输入含日内标签')
        raw['date'] = dates.dt.strftime('%Y-%m-%d')
        commercial[name] = date_window(dated(raw.rename(columns={'Close': 'value'})[['date', 'value']], 'date'), end, cutoff)
        meta = json.loads((imports / f'{name}-retrieval.json').read_text())
        if meta['source_id'] != ticker or meta['interval'] != '1d':
            raise ValueError('Yahoo日度请求元数据不符')
        sources[name] = {**meta, 'raw_sha256': digest(path), 'unit': 'index' if name == 'dxy' else 'USD/barrel',
                         'url': f'https://finance.yahoo.com/quote/{ticker.replace("=", "%3D")}/history/',
                         'frequency': 'D', 'timezone': 'New York date label', 'available_at': None,
                         'clock': 'daily Close time unverified; cutoff New York date excluded',
                         'revision_status': 'historical download',
                         'metadata_note': 'yfinance get_history_metadata requests 1h scheduling data separately; price request and date labels are daily'}
    path = imports / 'spdr-archive.xlsx'
    commercial['gld_holdings'] = date_window(gld_holdings(pd.read_excel(
        path, sheet_name='US GLD Historical Archive', usecols=['Date', 'Tonnes of Gold'])), end, cutoff)
    sources['gld_holdings'] = {**json.loads((imports / 'gld_holdings-retrieval.json').read_text()),
                              'source_id': 'SPDR GLD issuer archive', 'raw_sha256': digest(path), 'unit': 'tonnes',
                              'frequency': 'D', 'timezone': 'issuer date label', 'available_at': None,
                              'clock': 'publication time unverified; cutoff New York date excluded',
                              'revision_status': 'historical download', 'rights': 'local only; no redistribution consent'}
    gaps = []
    for meeting in C.GOLD_RESEARCH_FEDWATCH_MEETINGS:
        name = f'fedwatch_{meeting.replace("-", "")}'
        path = imports / f'{name}-raw.csv'
        try:
            commercial[name] = date_window(checked_fedwatch(path), end, cutoff)
        except (ValueError, OSError) as error:
            gaps.append({'source_id': name, 'meeting': meeting, 'status': 'unavailable',
                         'error': 'missing_export' if isinstance(error, OSError) else 'invalid_export',
                         'raw_sha256': digest(path) if path.exists() else None,
                         'fallback': 'original official series ends Sep 8; Reuters Sep 10 approximate snapshot remains separate'})
        else:
            sources[name] = {**json.loads((imports / f'{name}-retrieval.json').read_text()),
                             'raw_sha256': digest(path), 'unit': '% and original fraction buckets', 'frequency': 'D',
                             'timezone': 'date only', 'available_at': None, 'revision_status': 'historical export'}
    coverage = []
    for name, frame in {**frames, **commercial}.items():
        column = 'close' if name == 'gold' else 'tonnes' if name == 'gld_holdings' else 'higher_pct' if name.startswith('fedwatch') else 'value'
        if np.isinf(frame[column].to_numpy()).any() or (frame[column].dropna() < 0).any():
            raise ValueError(f'{name}包含非法值')
        index = pd.Index(frame['bar_end']) if name == 'gold' else pd.Index(frame['observation_date']) if name in frames else frame.index
        valid = index[frame[column].notna()]
        if valid.empty:
            raise ValueError(f'{name}没有有效观测')
        coverage.append({'series': name, 'first': str(index[0]), 'last_label': str(index[-1]),
                         'latest_observation': str(valid[-1]), 'rows': len(frame),
                         'missing_values': int(frame[column].isna().sum()), 'source': sources[name]})
    # All parsing/validation above succeeds before creating immutable output directories.
    for target, group in ((public, frames), (private, commercial)):
        target.mkdir(parents=True)
        for name, frame in group.items():
            frame.to_csv(target / f'{name}.csv', index=name not in frames and name != 'gold', index_label='date')
        write_json(target / 'manifest.json', {'phase': 4, 'cutoff_at': cutoff.isoformat(), 'created_at': utc_now(),
                                             'files': {p.name: digest(p) for p in sorted(target.iterdir())}})
    selection = {'phase': 4, 'snapshot': snapshot_id, 'information_cutoff_at': cutoff.isoformat(),
                 'sample_end': sample_end.isoformat(), 'created_at': utc_now(), 'coverage': coverage, 'gaps': gaps,
                 'evidence_sha256': digest(evidence_path),
                 'public_manifest_sha256': digest(public / 'manifest.json'),
                 'local_manifest_sha256': digest(private / 'manifest.json'),
                 'prior_selections': {str(p): digest(root / p) for p in (
                     Path('data/raw/gold-outlook/phase1/intraday-input.json'),
                     Path('data/raw/gold-outlook/phase2/inputs.json'), Path('data/raw/gold-outlook/phase3/inputs.json'))},
                 'commercial_boundary': 'raw exports, full normalized commercial series and plots remain in ignored local storage',
                 'availability_limit': 'historical exports acquired after cutoff; only completed prior dates retained, not proof of first publication time',
                 'carried_forward': {'cot': 'Sep 1 positions, Sep 4 release; next Sep 11 15:30 NY is after cutoff',
                                     'fedwatch': 'Sep 8 official historical exports; not extended with news estimates'}}
    write_json(phase / 'inputs.json', selection)
    return phase / 'inputs.json'


def load_update(root: Path = C.ROOT) -> tuple[dict, dict, dict]:
    phase = root / PHASE
    selection = json.loads((phase / 'inputs.json').read_text())
    snapshot_id = selection['snapshot']
    if not re.fullmatch(r'\d{8}T\d{6}Z', snapshot_id):
        raise ValueError('非法更新快照标识')
    for name, expected in selection['prior_selections'].items():
        if digest(root / name) != expected:
            raise ValueError('此前阶段的输入选择变化')
    if digest(phase / 'evidence.json') != selection['evidence_sha256']:
        raise ValueError('更新证据发生变化')
    frames = {}
    for public in (True, False):
        base = phase if public else root / '.cache/gold-outlook/phase4'
        path = base / 'snapshots' / snapshot_id
        if digest(path / 'manifest.json') != selection['public_manifest_sha256' if public else 'local_manifest_sha256']:
            raise ValueError('更新快照manifest发生变化')
        manifest = verify_snapshot(path)
        if timestamp(manifest['cutoff_at']) != timestamp(selection['information_cutoff_at']):
            raise ValueError('更新快照截止不符')
        for file in manifest['files']:
            frame = pd.read_csv(path / file)
            if file == 'gold.csv':
                prices = pd.Series(frame.close.to_numpy(), index=pd.to_datetime(frame.bar_end, utc=True))
                if prices.index[-1] != pd.Timestamp(selection['sample_end']):
                    raise ValueError('更新行情终点变化')
                frames['gold'] = checked_series(prices)
            else:
                frames[Path(file).stem] = dated(frame, 'observation_date' if public else 'date')
                if public:
                    known = pd.to_datetime(frame.known_by_at, utc=True)
                    if (frame.value.notna() & (known.isna() | (known > pd.Timestamp(selection['information_cutoff_at'])))).any():
                        raise ValueError('更新宏观数据在截止时不可用')
    return frames, selection, json.loads((phase / 'evidence.json').read_text())


def update_statistics(new: dict, old: dict, old_gold: pd.Series, provenance: dict, evidence: dict) -> dict:
    prices = new['gold']
    comparisons = {'gold': compare_versions(daily_closes(old_gold), daily_closes(prices))}
    for key in ('ust2y', 'ust10y', 'real10y', 'real5y', 'breakeven10y', 'usd_broad', 'wti', 'dxy', 'wti_futures', 'gld_holdings'):
        col = 'tonnes' if key == 'gld_holdings' else 'value'
        comparisons[key] = compare_versions(old[key][col], new[key][col].loc[BASELINE:])
    gold_overlap = old_gold.index.intersection(prices.index)
    overlap = compare_versions(old_gold.loc[gold_overlap], prices.loc[gold_overlap])
    shared = pd.concat({'gold': daily_closes(prices), 'ust2y': new['ust2y'].value,
                        'real10y': new['real10y'].value}, axis=1).loc['2026-09-08':].dropna()
    return {'phase': 4, 'inputs_sha256': digest(C.ROOT / PHASE / 'inputs.json'),
            'information_cutoff_at': provenance['information_cutoff_at'], 'data_as_of': str(pd.Timestamp(provenance['sample_end']).date()),
            'basis': 'GCZ26 five-minute Close, 17:00 New York endpoints; historical phases remain fixed',
            'comparisons': comparisons,
            'gold_overlap': {'rows': len(gold_overlap), 'revised_rows': len(overlap['revised_overlap_dates']),
                             'missing_baseline_bars': len(old_gold.loc[prices.index[0]:].index.difference(prices.index))},
            'overall': interval_stats(prices, f'{BASELINE}T17:00:00-04:00', provenance['sample_end']),
            'latest_daily_closes': {d.date().isoformat(): float(v) for d, v in daily_closes(prices).loc['2026-09-08':].items()},
            'same_date_rates_and_gold': json.loads(shared.to_json(orient='index', date_format='iso')),
            'calendar': future_calendar(evidence['calendar'], provenance['information_cutoff_at'])}
