"""Phase 2: freeze supplemental inputs and analyse observed dates without filling."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from inv import config as C
from inv.gold_analysis import AS_OF, BASELINE
from inv.gold_data import timestamp, utc_now, verify_snapshot

MACRO_ID = '20260909T115946Z'
INFORMATION_CUTOFF = '2026-09-09T11:59:46Z'
MACRO_NAMES = ('ust2y', 'ust10y', 'real10y', 'real5y', 'breakeven10y', 'usd_broad', 'wti',
               'ffr_target_lower', 'ffr_target_upper')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def dated(frame: pd.DataFrame, column: str, *, fmt: str = '%Y-%m-%d') -> pd.DataFrame:
    result = frame.copy()
    dates = pd.DatetimeIndex(pd.to_datetime(result.pop(column), format=fmt, errors='raise'), name='date')
    if dates.has_duplicates or dates.hasnans:
        raise ValueError('日期缺失或重复')
    result.index = dates
    return result.sort_index()


def date_window(frame: pd.DataFrame, end: str, cutoff: datetime) -> pd.DataFrame:
    """Unknown daily clocks: conservatively exclude the cutoff's whole New York date."""
    last_complete = pd.Timestamp(cutoff).tz_convert('America/New_York').date()
    return frame.loc[(frame.index >= BASELINE) & (frame.index <= end) & (frame.index.date < last_complete)]


def fedwatch(frame: pd.DataFrame, current: tuple[int, int] = (350, 375)) -> pd.DataFrame:
    """Buckets are fractions; higher means target ABOVE today's range, not a meeting action."""
    result = dated(frame, 'Date', fmt='%m/%d/%Y')
    bands = {}
    for col in result:
        match = re.fullmatch(r'\((\d+)-(\d+)\)', col)
        if not match:
            raise ValueError('未知 FedWatch 概率列')
        low, high = map(int, match.groups())
        if high - low != 25 or low % 25:
            raise ValueError('FedWatch 区间不是25基点网格')
        bands[col] = (low, high)
    if current not in bands.values():
        raise ValueError('缺少当前目标区间')
    values = result.apply(pd.to_numeric, errors='raise')
    # CME leaves extreme targets blank. Retain the blanks and require the populated mass to sum to one.
    inside = values.notna().cummax(axis=1) & values.notna().iloc[:, ::-1].cummax(axis=1).iloc[:, ::-1]
    if (inside & values.isna()).any().any():
        raise ValueError('FedWatch 概率分布内部缺失')
    if np.isinf(values.to_numpy()).any() or ((values < 0) | (values > 1)).any().any():
        raise ValueError('FedWatch 必须使用0—1概率')
    if not np.allclose(values.sum(axis=1), 1, atol=5e-6, rtol=0):
        raise ValueError('FedWatch 概率之和不为1')
    result = values.copy()  # retain the original full target distribution
    for name, cols in {
        'lower_pct': [c for c, (low, high) in bands.items() if high <= current[0]],
        'unchanged_pct': [c for c, band in bands.items() if band == current],
        'higher_pct': [c for c, (low, high) in bands.items() if low >= current[1]],
    }.items():
        result[name] = values[cols].sum(axis=1) * 100
    return result


def gld_holdings(frame: pd.DataFrame) -> pd.DataFrame:
    result = dated(frame[['Date', 'Tonnes of Gold']], 'Date', fmt='%d-%b-%Y')
    raw = result['Tonnes of Gold']
    # The issuer labels US holidays explicitly. Do not silently coerce corrupt observations.
    values = pd.to_numeric(raw.mask(raw.eq('US Holiday')), errors='raise')
    if raw.isna().any() or ((values.notna()) & ((values <= 0) | ~np.isfinite(values))).any():
        raise ValueError('GLD持金量缺失或无效')
    return pd.DataFrame({'tonnes': values, 'holiday': raw.eq('US Holiday')})


def released_cot(frame: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    result = dated(frame, 'observation_date')
    available = pd.to_datetime(result.available_at, utc=True, errors='raise')
    result = result.loc[available.notna() & (available <= pd.Timestamp(cutoff))].copy()
    cols = ['managed_money_long', 'managed_money_short', 'managed_money_spreading', 'open_interest', 'value']
    result[cols] = result[cols].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(result[cols].to_numpy()).all():
        raise ValueError('CFTC存在缺失持仓')
    if (result[cols[:-1]] < 0).any().any() or (result[cols[:-1]] % 1 != 0).any().any():
        raise ValueError('CFTC合约数量必须为非负整数')
    if not result.value.eq(result.managed_money_long - result.managed_money_short).all():
        raise ValueError('CFTC净额与多空头不一致')
    result['long_change'] = result.managed_money_long.diff()
    result['short_contribution'] = -result.managed_money_short.diff()
    result['net_change'] = result.value.diff()
    # A missing weekly report must not be represented as a one-week change.
    irregular = result.index.to_series().diff().ne(pd.Timedelta(days=7))
    result.loc[irregular, ['long_change', 'short_contribution', 'net_change']] = np.nan
    return result


def common_change(series: dict[str, pd.Series], start: str, end: str) -> dict:
    """Only use dates actually observed by EVERY input; report any shortened end."""
    common = pd.concat(series, axis=1).loc[start:end].dropna()
    if common.empty or common.index[0] != pd.Timestamp(start):
        raise ValueError('共同样本缺少起始观测')
    return {'start': start, 'requested_end': end, 'end': common.index[-1].date().isoformat(),
            'values': {key: {'start': float(common[key].iloc[0]), 'end': float(common[key].iloc[-1]),
                             'change': float(common[key].iloc[-1] - common[key].iloc[0]),
                             'change_pct': float((common[key].iloc[-1] / common[key].iloc[0] - 1) * 100)}
                       for key in common}}


def freeze_drivers(cutoff: datetime, *, refresh: bool = False, root: Path = C.ROOT) -> Path:
    """Explicit acquisition only; analysis loads the fixed selection written here."""
    if cutoff != timestamp(INFORMATION_CUTOFF):
        raise ValueError('Phase 2沿用基准截止；改变截止需要新研究阶段')
    base = root / '.cache/gold-outlook'
    downloads = base / 'phase2/downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    if refresh:
        from inv.fetch_market import _download
        for name, ticker in C.GOLD_RESEARCH_DRIVER_MARKETS.items():
            frame = _download(ticker, start='2026-07-01')
            if frame is None or frame.empty:
                raise ValueError(f'Yahoo 下载失败：{ticker}')
            frame.to_csv(downloads / f'{name}.csv', index_label='date')
            write_json(downloads / f'{name}-retrieval.json', {
                'source_id': ticker, 'retrieved_at': utc_now(), 'interval': '1d', 'auto_adjust': False})
    frames, sources = {}, {}
    for name, ticker in C.GOLD_RESEARCH_DRIVER_MARKETS.items():
        path = downloads / f'{name}.csv'
        frame = dated(pd.read_csv(path), 'date')
        frame = date_window(frame, AS_OF, cutoff)
        price = pd.to_numeric(frame.close, errors='raise')
        if frame.empty or ((price.notna()) & ((price <= 0) | ~np.isfinite(price))).any():
            raise ValueError('Yahoo 驱动价格无效')
        frames[name] = pd.DataFrame({'value': price})
        sources[name] = {**json.loads((downloads / f'{name}-retrieval.json').read_text()),
                         'url': f'https://finance.yahoo.com/quote/{ticker.replace("=", "%3D")}/history/',
                         'raw_sha256': digest(path), 'unit': 'index' if name == 'dxy' else 'USD/barrel',
                         'clock': 'Yahoo daily label; exact Close clock unverified', 'frequency': 'D'}
    paths = ['fedwatch_csv', 'fedwatch-20261028.csv', 'fedwatch-20261209.csv']
    for meeting, filename in zip(C.GOLD_RESEARCH_FEDWATCH_MEETINGS, paths, strict=True):
        name = 'fedwatch_' + meeting.replace('-', '')
        path = base / 'tun-retry/node2' / filename
        raw = pd.read_csv(path)
        dates = pd.to_datetime(raw.Date, format='%m/%d/%Y')
        raw = raw.loc[(dates >= BASELINE) & (dates <= AS_OF)]
        frames[name] = date_window(fedwatch(raw), AS_OF, cutoff)
        sources[name] = {'source_id': 'CME FedWatch', 'meeting': meeting, 'unit': 'fraction; derived columns in %',
                         'retrieved_at': '2026-09-09T12:46:00.602471Z', 'raw_sha256': digest(path),
                         'url': 'https://www.cmegroup.com/tools-information/quikstrike/cme-fedwatch-tool-user-guide.html',
                         'current_target_bp': [350, 375], 'frequency': 'D',
                         'clock': 'Export date only; exact observation/release clock unverified'}
        sources[name]['missing_buckets'] = 'Leading/trailing unpopulated targets retained as missing; populated mass must sum to 1 within 5e-6'
    path = base / 'probes/spdr-archive.bin'
    frames['gld_holdings'] = date_window(gld_holdings(pd.read_excel(
        path, sheet_name='US GLD Historical Archive', usecols=['Date', 'Tonnes of Gold'])), AS_OF, cutoff)
    sources['gld_holdings'] = {'source_id': 'SPDR GLD issuer archive', 'raw_sha256': digest(path),
                              'url': 'https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en',
                              'retrieved_at': '2026-09-09T12:13:17Z', 'unit': 'tonnes', 'frequency': 'D',
                              'clock': 'Issuer observation date; publication clock unknown',
                              'rights': 'Issuer prohibits redistribution without prior written consent; local cache only'}
    created = utc_now()
    snapshot_id = timestamp(created).strftime('%Y%m%dT%H%M%SZ')
    target = base / 'phase2/snapshots' / snapshot_id
    target.mkdir(parents=True, exist_ok=False)
    for name, frame in frames.items():
        if frame.empty or frame.index[0] != pd.Timestamp(BASELINE):
            raise ValueError(f'{name} 缺少7月末基准')
        frame.to_csv(target / f'{name}.csv', index_label='date')
        numeric = frame.select_dtypes('number')
        sources[name].update({'first': frame.index[0].date().isoformat(),
                              'last': frame.index[-1].date().isoformat(), 'rows': len(frame),
                              'missing_numeric_cells': int(numeric.isna().sum().sum()),
                              'revision_status': 'historical download, not archived first release',
                              'baseline_status': 'retrospective supplement acquired after information cutoff',
                              'timezone': 'date labels only', 'available_at': None})
    write_json(target / 'sources.json', sources)
    manifest = {'phase': 2, 'cutoff_at': INFORMATION_CUTOFF, 'sample_end': AS_OF, 'created_at': created,
                'files': {p.name: digest(p) for p in sorted(target.iterdir())}}
    write_json(target / 'manifest.json', manifest)
    verify_snapshot(target)
    phase = root / 'data/raw/gold-outlook/phase2'
    phase.mkdir(parents=True, exist_ok=True)
    selection = {'phase': 2, 'macro_snapshot': MACRO_ID, 'supplement_snapshot': snapshot_id,
                 'information_cutoff_at': INFORMATION_CUTOFF, 'sample_end': AS_OF,
                 'supplement_files': manifest['files'], 'sources': sources,
                 'macro_manifest_sha256': digest(root / f'data/raw/gold-outlook/snapshots/{MACRO_ID}/manifest.json'),
                 'intraday_selection_sha256': digest(root / 'data/raw/gold-outlook/phase1/intraday-input.json'),
                 'publication': 'full supplemental inputs and plots local-only; derived report findings for review'}
    write_json(phase / 'inputs.json', selection)
    return target


def load_drivers(root: Path = C.ROOT) -> tuple[dict, dict]:
    phase = root / 'data/raw/gold-outlook/phase2'
    selection = json.loads((phase / 'inputs.json').read_text())
    macro = root / 'data/raw/gold-outlook/snapshots' / selection['macro_snapshot']
    supplement_id = selection['supplement_snapshot']
    if not re.fullmatch(r'\d{8}T\d{6}Z', supplement_id) or selection['macro_snapshot'] != MACRO_ID:
        raise ValueError('驱动快照选择非法')
    if digest(macro / 'manifest.json') != selection['macro_manifest_sha256']:
        raise ValueError('宏观快照版本变化')
    if digest(root / 'data/raw/gold-outlook/phase1/intraday-input.json') != selection['intraday_selection_sha256']:
        raise ValueError('黄金日内输入选择变化；需要显式更新 Phase 2')
    manifest = verify_snapshot(macro)
    if timestamp(manifest['cutoff_at']) != timestamp(INFORMATION_CUTOFF):
        raise ValueError('宏观信息截止不符')
    supplement = root / '.cache/gold-outlook/phase2/snapshots' / supplement_id
    if verify_snapshot(supplement)['files'] != selection['supplement_files']:
        raise ValueError('补充快照哈希与所选记录不符')
    frames = {}
    for name in MACRO_NAMES:
        df = dated(pd.read_csv(macro / f'{name}.csv'), 'observation_date')
        known = pd.to_datetime(df.known_by_at, utc=True)
        if (df.value.notna() & (known.isna() | (known > pd.Timestamp(INFORMATION_CUTOFF)))).any():
            raise ValueError('宏观值在截止时尚不可知')
        frames[name] = df.loc[BASELINE:AS_OF, ['value']]
    for name in selection['sources']:
        frames[name] = dated(pd.read_csv(supplement / f'{name}.csv'), 'date')
    frames['cot'] = released_cot(pd.read_csv(macro / 'cot_gold.csv'), INFORMATION_CUTOFF)
    frames['cot'] = frames['cot'].loc['2026-07-28':AS_OF]
    for key, target in [('ffr_target_lower', 3.5), ('ffr_target_upper', 3.75)]:
        if not frames[key].value.dropna().eq(target).all():
            raise ValueError('目标利率发生变化；不能使用固定FedWatch比较区间')
    return frames, {'selection_sha256': digest(phase / 'inputs.json'),
                    'evidence_sha256': digest(phase / 'evidence.json'), **selection}


def driver_statistics(frames: dict, gold: pd.Series, provenance: dict) -> dict:
    local = gold.tz_convert('America/New_York')
    daily = local.loc[(local.index.hour == 17) & (local.index.minute == 0)].copy()
    daily.index = daily.index.tz_localize(None).normalize()
    macro = {k: frames[k].value for k in MACRO_NAMES[:7]}
    nominal_real = pd.concat({k: macro[k] for k in ['ust10y', 'real10y', 'breakeven10y']}, axis=1).dropna()
    residual = (nominal_real.ust10y - nominal_real.real10y - nominal_real.breakeven10y) * 100
    if residual.abs().max() > 2 + 1e-8:
        raise ValueError('同期限名义/实际/通胀补偿差异超过2基点')
    windows = [(BASELINE, '2026-08-07'), ('2026-08-07', '2026-08-18'),
               ('2026-08-18', '2026-08-25'), ('2026-08-25', AS_OF)]
    groups = {'rates': ['ust2y', 'ust10y', 'real10y', 'real5y', 'breakeven10y'],
              'dollar': ['dxy', 'usd_broad'], 'oil': ['wti', 'wti_futures'],
              'gld': ['gld_holdings'], 'policy': ['fedwatch_20260916', 'fedwatch_20261028', 'fedwatch_20261209']}
    comparisons = {}
    for group, keys in groups.items():
        series = {key: frames[key]['higher_pct' if key.startswith('fedwatch') else
                                    'tonnes' if key == 'gld_holdings' else 'value'] for key in keys}
        comparisons[group] = [common_change({'gold': daily, **series}, start, end) for start, end in windows]
    endpoints = [BASELINE, '2026-08-07', '2026-08-18', '2026-08-25', '2026-09-01', '2026-09-04', AS_OF]
    selected = {'gold': daily}
    for name, frame in frames.items():
        if name != 'cot':
            selected[name] = frame['higher_pct' if name.startswith('fedwatch') else
                                   'tonnes' if name == 'gld_holdings' else 'value']
    levels = pd.concat(selected, axis=1).reindex(pd.to_datetime(endpoints))
    cot = frames['cot'].reset_index()
    cot['date'] = cot.date.dt.strftime('%Y-%m-%d')
    return {'phase': 2, 'data_as_of': AS_OF, 'inputs': provenance,
            'unit_conventions': {'rates': 'levels in percent; change in percentage points, multiply by 100 for basis points',
                                 'policy': 'levels in percent; change in percentage points',
                                 'gold': 'USD/troy oz', 'gld_holdings': 'tonnes', 'cot': 'contracts'},
            'comparisons': comparisons, 'rate_decomposition_max_residual_bp': float(residual.abs().max()),
            'levels': json.loads(levels.to_json(orient='index', date_format='iso')),
            'cot': json.loads(cot.to_json(orient='records')),
            'limits': ['Observation-date comparisons; different market close clocks.',
                       'COT filtered by release time; historical archive can contain later revisions.',
                       'Supplemental historical downloads are not first-release vintages.',
                       'No interpolation, contribution attribution or causal regression.']}
