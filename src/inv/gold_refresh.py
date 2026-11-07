"""Immutable Phase 0 refresh runs with a public government-data boundary."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, time, timedelta, timezone
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from inv import config as C
from inv.gold_data import verify_snapshot
from inv.gold_refresh_government import fetch_government
from inv.gold_refresh_sources import fetch_yahoo
from inv.gold_refresh_supplement import fetch_gld, normalize_fedwatch

NY = ZoneInfo('America/New_York')
UTC = timezone.utc
PRICE_FIELDS = ['open', 'high', 'low', 'close', 'volume']
DAILY_UNITS = {'primary_daily': 'USD/troy oz', 'history_daily': 'USD/troy oz',
               'dxy_daily': 'index points', 'wti_futures_daily': 'USD/barrel'}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=_jsonable) + '\n', encoding='utf-8')


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('cutoff 必须是带时区的 datetime')
    return value


def _date(value: str, name: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} 必须是 YYYY-MM-DD') from exc
    if pd.isna(result) or result.tzinfo is not None or result.strftime('%Y-%m-%d') != value:
        raise ValueError(f'{name} 必须是 YYYY-MM-DD')
    return result


def _jsonable(value):
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.name
    raise TypeError(f'不支持的JSON类型: {type(value).__name__}')


def _metadata_record(frame: pd.DataFrame, meta: dict, *, source: str, source_id: str, url: str,
                     unit: str, frequency: str, timezone_name: str, date_column: str = 'observation_date') -> dict:
    dates = frame[date_column].astype(str) if len(frame) else pd.Series(dtype=str)
    numeric = frame.select_dtypes(include='number')
    value_field = next((field for field in ('value', 'close', 'tonnes') if field in frame), None)
    valid = frame[value_field].notna() if value_field else pd.Series(False, index=frame.index)
    observed = dates.loc[valid] if len(frame) else dates
    return {'status': 'downloaded', 'source': source, 'source_id': source_id, 'url': url,
            'unit': unit, 'frequency': frequency, 'timezone': timezone_name,
            'retrieved_at': meta.get('retrieved_at'), 'first_publication_unknown': True,
            'first_observation': observed.min() if len(observed) else None,
            'last_observation': observed.max() if len(observed) else None,
            'last_row_date': dates.max() if len(dates) else None,
            'rows': len(frame), 'valid_rows': int(valid.sum()),
            'missing_rows': int(numeric.isna().any(axis=1).sum()) if len(frame) else 0}


def _check_prices(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    if set(['date', *PRICE_FIELDS]) - set(frame):
        raise ValueError(f'{label} 缺少日线 OHLCV')
    out = frame[['date', *PRICE_FIELDS]].copy()
    dates = pd.to_datetime(out.date, format='%Y-%m-%d', errors='raise')
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError(f'{label} 日期必须唯一且递增')
    out[PRICE_FIELDS] = out[PRICE_FIELDS].apply(pd.to_numeric, errors='raise')
    values = out[PRICE_FIELDS].to_numpy(dtype=float)
    if np.isinf(values).any():
        raise ValueError(f'{label} 包含无穷值')
    full = out[['open', 'high', 'low', 'close']].notna().all(axis=1)
    if ((out[['open', 'high', 'low', 'close']] <= 0) & out[['open', 'high', 'low', 'close']].notna()).any().any() or (out.volume < 0).any():
        raise ValueError(f'{label} 价格或成交量非法')
    if ((out.high < out[['open', 'close', 'low']].max(axis=1)) & full).any() or (
        (out.low > out[['open', 'close', 'high']].min(axis=1)) & full
    ).any():
        raise ValueError(f'{label} OHLC 高低关系不一致')
    out['date'] = dates.dt.strftime('%Y-%m-%d')
    return out


def _validate_main(frame: pd.DataFrame, focus_start: str, sample_end: str) -> dict:
    dates = pd.to_datetime(frame.date, format='%Y-%m-%d')
    complete = frame[['open', 'high', 'low', 'close']].notna().all(axis=1)
    baseline_candidates = frame.loc[(dates < pd.Timestamp(focus_start)) & complete]
    focus = frame.loc[(dates >= pd.Timestamp(focus_start)) & (dates <= pd.Timestamp(sample_end))]
    baseline_date = baseline_candidates.date.max() if len(baseline_candidates) else None
    end_row = frame.loc[frame.date.eq(sample_end)]
    focus_values = focus[['open', 'high', 'low', 'close']].to_numpy(dtype=float)
    focus_valid = bool(len(focus) and np.isfinite(focus_values).all() and
                       (focus[['open', 'high', 'low', 'close']] > 0).all().all())
    endpoint_valid = bool(len(end_row) == 1 and end_row[['open', 'high', 'low', 'close']].notna().all().all()
                          and np.isfinite(end_row[['open', 'high', 'low', 'close']].to_numpy(dtype=float)).all()
                          and (end_row[['open', 'high', 'low', 'close']] > 0).all().all())
    return {'baseline_date': baseline_date, 'baseline_ready': baseline_date is not None,
            'sample_end_present': endpoint_valid,
            'focus_rows': len(focus), 'focus_prices_valid': focus_valid,
            'ready': baseline_date is not None and endpoint_valid and focus_valid}


def _price_check_table(frame: pd.DataFrame, focus_start: str, sample_end: str) -> pd.DataFrame:
    focus = frame.loc[frame.date.between(focus_start, sample_end)]
    high_rows = focus.dropna(subset=['high'])
    close_rows = focus.dropna(subset=['close'])
    rows = []
    baseline = frame.loc[frame.date < focus_start].dropna(subset=['close'])
    candidates = [
        ('baseline', baseline.sort_values('date').iloc[-1] if len(baseline) else None),
        ('highest_high_day', high_rows.sort_values(['high', 'date'], ascending=[False, True]).iloc[0] if len(high_rows) else None),
        ('highest_close_day', close_rows.sort_values(['close', 'date'], ascending=[False, True]).iloc[0] if len(close_rows) else None),
        ('latest_day', focus.sort_values('date').iloc[-1] if len(focus) else None),
    ]
    for kind, row in candidates:
        rows.append({'check': kind, **({k: row[k] for k in ['date', *PRICE_FIELDS]} if row is not None else
                                      {k: '' for k in ['date', *PRICE_FIELDS]}),
                     'method': 'observed daily OHLCV only; no return or drawdown calculated'})
    return pd.DataFrame(rows)


def _validated_etf_import(path: Path, cutoff: datetime, sample_end: str) -> tuple[pd.DataFrame, dict]:
    frame = pd.read_csv(path)
    required = {'observation_date', 'known_by_at'}
    measures = {'flows_usd', 'flow_tonnes', 'holdings_tonnes'} & set(frame.columns)
    if required - set(frame) or not measures:
        raise ValueError('ETF输入需含observation_date、known_by_at和规范化的流量或持仓列')
    dates = pd.to_datetime(frame.observation_date, format='%Y-%m-%d', errors='raise')
    if dates.duplicated().any():
        raise ValueError('ETF observation_date 重复')
    known = pd.to_datetime(frame.known_by_at, utc=True, errors='raise')
    if known.isna().any():
        raise ValueError('ETF known_by_at 不能缺失')
    for field in measures:
        frame[field] = pd.to_numeric(frame[field], errors='raise')
        if np.isinf(frame[field].to_numpy(dtype=float)).any():
            raise ValueError(f'ETF {field} 含无穷值')
    keep = (dates <= pd.Timestamp(sample_end)) & (known <= pd.Timestamp(cutoff).tz_convert('UTC'))
    frame = frame.loc[keep].copy()
    frame['observation_date'] = dates.loc[keep].dt.strftime('%Y-%m-%d')
    frame['known_by_at'] = known.loc[keep].map(lambda value: value.isoformat())
    field_units = {'flows_usd': 'USD', 'flow_tonnes': 'tonnes', 'holdings_tonnes': 'tonnes'}
    return frame.reset_index(drop=True), {'measures': sorted(measures),
        'units': {field: field_units[field] for field in measures},
        'frequency': 'M',
        'first_observation': frame.observation_date.min() if len(frame) else None,
        'last_observation': frame.observation_date.max() if len(frame) else None,
        'last_row_date': frame.observation_date.max() if len(frame) else None,
        'rows': len(frame), 'valid_rows': int(frame[list(measures)].notna().any(axis=1).sum()) if len(frame) else 0,
        'missing_rows': int(frame[list(measures)].isna().all(axis=1).sum()) if len(frame) else 0}


def _save_yahoo(frame: pd.DataFrame, meta: dict, ticker: str, interval: str, name: str,
                local_stage: Path, public_stage: Path | None = None) -> tuple[pd.DataFrame, dict]:
    meta = dict(meta)
    raw = meta.pop('raw_response', None)
    if raw is not None:
        _write_json(local_stage / 'downloads' / f'{name}-raw.json', raw)
    _write_json(local_stage / 'downloads' / f'{name}-retrieval.json',
                {k: v for k, v in meta.items() if k not in {'request_start', 'request_end'}})
    source = {'source': 'Yahoo Finance', 'source_id': ticker,
              'url': f'https://finance.yahoo.com/quote/{ticker.replace("=", "%3D")}/history/',
              'unit': 'USD/troy oz' if ticker.startswith('GC') else 'index points' if ticker == 'DX-Y.NYB' else 'USD/barrel',
              'frequency': interval, 'timezone': meta.get('exchangeTimezoneName'),
              'retrieved_at': meta.get('retrieved_at'), 'first_publication_unknown': True}
    return frame, source


def freeze_refresh(cutoff: datetime, *, focus_start: str, background_start: str, sample_end: str,
                   refresh: bool, public_root: Path, local_root: Path, evidence: Path,
                   imports: Path | None = None) -> Path:
    cutoff = _aware(cutoff)
    if not refresh:
        raise ValueError('freeze_refresh 只接受 refresh=True；已保存run请使用 verify_refresh')
    if cutoff.astimezone(UTC) > datetime.now(UTC):
        raise ValueError('cutoff 不能位于未来')
    focus, background, end = (_date(focus_start, 'focus_start'), _date(background_start, 'background_start'),
                              _date(sample_end, 'sample_end'))
    if background < pd.Timestamp('2023-08-01') or background > focus or focus > end:
        raise ValueError('日期必须满足 2023-08-01 <= background_start <= focus_start <= sample_end')
    if end.date() >= cutoff.astimezone(NY).date():
        raise ValueError('sample_end 必须早于 cutoff 的纽约日期')
    evidence = Path(evidence)
    evidence_data = json.loads(evidence.read_text(encoding='utf-8'))
    release_times = evidence_data.get('cftc_release_times', {})
    if not isinstance(release_times, dict):
        raise ValueError('evidence.cftc_release_times 必须是对象')
    run_id = cutoff.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')
    relative = Path('runs') / run_id
    public_root, local_root = Path(public_root), Path(local_root)
    public_target, local_target = public_root / relative, local_root / relative
    public_tmp, local_tmp = public_root / 'runs' / f'{run_id}.tmp', local_root / 'runs' / f'{run_id}.tmp'
    if any(p.exists() for p in (public_target, local_target, public_tmp, local_tmp)):
        raise ValueError('public/local run 或 staging 已存在；拒绝覆盖')
    public_tmp.mkdir(parents=True)
    local_tmp.mkdir(parents=True)
    try:
        support_relative = evidence_data.get('supporting_local_directory')
        if support_relative:
            support_path = local_root.joinpath(*_safe_relative(support_relative).parts)
            _inside(support_path, local_root)
            if not support_path.is_dir():
                raise ValueError('evidence supporting_local_directory 不存在或不是目录')
            for source in support_path.rglob('*'):
                if source.is_symlink():
                    _inside(source, support_path)
                    raise ValueError('supporting_local_directory 不允许符号链接')
                _inside(source, support_path)
            shutil.copytree(support_path, local_tmp / 'downloads' / 'support')

        records: dict[str, dict] = {}
        public_frames: dict[str, pd.DataFrame] = {}
        local_frames: dict[str, pd.DataFrame] = {}
        daily_specs = {name: (ticker, DAILY_UNITS[name])
                       for name, ticker in C.GOLD_RESEARCH_REFRESH_MARKETS.items()}
        if set(daily_specs) != set(DAILY_UNITS):
            raise ValueError('GOLD_RESEARCH_REFRESH_MARKETS 必须登记四个日线系列')
        daily_windows = {
            'primary_daily': focus - pd.Timedelta(days=10),
            'history_daily': background,
            'dxy_daily': focus - pd.Timedelta(days=10),
            'wti_futures_daily': focus - pd.Timedelta(days=10),
        }
        cutoff_utc = cutoff.astimezone(UTC)
        for name, (ticker, unit) in daily_specs.items():
            lower = daily_windows[name]
            start_dt = datetime.combine(lower.date(), time.min, NY)
            try:
                frame, meta = fetch_yahoo(ticker, '1d', start_dt, cutoff)
                frame = _check_prices(frame, name)
                frame = frame.loc[frame.date.between(lower.strftime('%Y-%m-%d'), sample_end)].reset_index(drop=True)
                local_frames[name] = frame
                records[name] = _metadata_record(frame, meta, source='Yahoo Finance', source_id=ticker,
                    url=f'https://finance.yahoo.com/quote/{ticker.replace("=", "%3D")}/history/', unit=unit,
                    frequency='1d', timezone_name=meta['exchangeTimezoneName'], date_column='date')
                _save_yahoo(frame, meta, ticker, '1d', name, local_tmp)
            except Exception as exc:
                records[name] = {'status': 'failed', 'source': 'Yahoo Finance', 'source_id': ticker,
                                 'url': f'https://finance.yahoo.com/quote/{ticker.replace("=", "%3D")}/history/',
                                 'unit': unit, 'frequency': '1d', 'timezone': None, 'retrieved_at': None,
                                 'first_publication_unknown': True, 'first_observation': None,
                                 'last_observation': None, 'missing_rows': None,
                                 'error_type': type(exc).__name__,
                                 'message': 'Yahoo daily series unavailable or invalid'}

        primary = local_frames.get('primary_daily', pd.DataFrame(columns=['date', *PRICE_FIELDS]))
        primary_check = _validate_main(primary, focus_start, sample_end) if len(primary) else {
            'baseline_date': None, 'baseline_ready': False, 'sample_end_present': False,
            'focus_rows': 0, 'focus_prices_valid': False, 'ready': False}
        gaps = {}
        if 'primary_daily' in local_frames and 'history_daily' in local_frames:
            p_dates = set(primary.loc[primary.date.between(focus_start, sample_end), 'date'])
            h_dates = set(local_frames['history_daily'].loc[
                local_frames['history_daily'].date.between(focus_start, sample_end), 'date'])
            gaps = {'primary_missing_from_history': sorted(h_dates - p_dates),
                    'history_missing_from_primary': sorted(p_dates - h_dates)}
            if gaps['primary_missing_from_history']:
                primary_check['ready'] = False
        else:
            gaps = {'primary_missing_from_history': [], 'history_missing_from_primary': [], 'status': 'comparison_unavailable'}
        business_days = pd.bdate_range(focus_start, sample_end).strftime('%Y-%m-%d').tolist()
        observed = set(primary.date) if len(primary) else set()
        pending = sorted(set(business_days) - observed)
        (local_tmp / 'price_checks.csv').parent.mkdir(parents=True, exist_ok=True)
        _price_check_table(primary, focus_start, sample_end).to_csv(local_tmp / 'price_checks.csv', index=False,
                                                                    lineterminator='\n')

        intraday_focus_start = datetime.combine((focus - pd.Timedelta(days=10)).date(), time.min, NY)
        intraday_start_dt = max(intraday_focus_start, cutoff_utc - timedelta(days=59))
        intraday_name = 'primary_intraday'
        intraday_end = pd.Timestamp(datetime.combine(end.date(), time(17), NY)).tz_convert('UTC')
        try:
            bars, intraday_meta = fetch_yahoo('GCZ26.CMX', '5m', intraday_start_dt, cutoff)
            bar_ends = pd.to_datetime(bars.timestamp, utc=True) + pd.Timedelta(minutes=5)
            valid_window = (bar_ends <= intraday_end) & (bar_ends <= pd.Timestamp(cutoff_utc))
            bars = bars.loc[valid_window].reset_index(drop=True)
            if bars.empty:
                raise ValueError('5m sample window contains no completed bars')
            local_frames[intraday_name] = bars
            records[intraday_name] = _metadata_record(bars, intraday_meta, source='Yahoo Finance',
                source_id='GCZ26.CMX', url='https://finance.yahoo.com/quote/GCZ26.CMX/history/',
                unit='USD/troy oz', frequency='5m', timezone_name=intraday_meta.get('exchangeTimezoneName'),
                date_column='timestamp')
            starts = pd.to_datetime(bars.timestamp, utc=True)
            bar_gaps = [{'previous_bar_end': (left + pd.Timedelta(minutes=5)).isoformat(),
                         'next_bar_start': right.isoformat(),
                         'elapsed_minutes': int((right - left) / pd.Timedelta(minutes=1))}
                        for left, right in zip(starts[:-1], starts[1:], strict=True)
                        if right - left > pd.Timedelta(minutes=5)]
            records[intraday_name].update({'timestamp_semantics': 'Yahoo timestamps are bar starts',
                'last_bar_end': (starts.iloc[-1] + pd.Timedelta(minutes=5)).isoformat(),
                'gap_count': len(bar_gaps), 'gaps': bar_gaps,
                'fill_policy': 'none; missing intervals remain gaps'})
            _save_yahoo(bars, intraday_meta, 'GCZ26.CMX', '5m', intraday_name, local_tmp)
        except Exception as exc:
            records[intraday_name] = {'status': 'gap', 'source': 'Yahoo Finance', 'source_id': 'GCZ26.CMX',
                                      'url': 'https://finance.yahoo.com/quote/GCZ26.CMX/history/',
                                      'unit': 'USD/troy oz', 'frequency': '5m', 'timezone': None,
                                      'retrieved_at': None, 'first_publication_unknown': True,
                                      'first_observation': None, 'last_observation': None, 'missing_rows': None,
                                      'error_type': type(exc).__name__,
                                      'message': 'Intraday bars unavailable; supporting data gap'}

        gov_dir = local_tmp / 'downloads'
        try:
            gov_frames, gov_records = fetch_government(cutoff, background_start, focus_start, gov_dir, release_times)
            for name, frame in gov_frames.items():
                public_frames[name] = frame.copy()
                record = gov_records.get(name, {})
                if 'observation_date' in frame:
                    dates = frame.observation_date.astype(str)
                    valid = frame.value.notna() if 'value' in frame else pd.Series(False, index=frame.index)
                    observed = dates.loc[valid]
                    record['first_observation'] = observed.min() if len(observed) else None
                    record['last_observation'] = observed.max() if len(observed) else None
                    record['last_row_date'] = dates.max() if len(dates) else None
                    record['rows'] = len(frame)
                    record['valid_rows'] = int(valid.sum())
                if 'missing_observations' in record:
                    record['missing_rows'] = record['missing_observations']
                if 'source_url' in record:
                    record['url'] = record['source_url']
                if 'provider' in record:
                    record['source'] = record['provider']
            for record in gov_records.values():
                record.setdefault('missing_rows', record.get('missing_observations'))
                if 'source_url' in record:
                    record.setdefault('url', record['source_url'])
                if 'provider' in record:
                    record.setdefault('source', record['provider'])
            records.update(gov_records)
        except Exception as exc:
            records['government_fetch'] = {'status': 'failed', 'error_type': type(exc).__name__,
                                           'message': 'Government series unavailable or invalid'}

        # Provider-owned gold ETF workbook remains in local storage; only bounded derived rows stay local.
        gld_start = datetime.combine((focus - pd.Timedelta(days=10)).date(), time.min, NY)
        try:
            gld, gld_meta = fetch_gld(gld_start, cutoff, gov_dir)
            gld = gld.loc[gld.date.between((focus - pd.Timedelta(days=10)).strftime('%Y-%m-%d'), sample_end)]
            local_frames['gld_holdings'] = gld.reset_index(drop=True)
            records['gld_holdings'] = _metadata_record(local_frames['gld_holdings'], gld_meta,
                source='SPDR Gold Shares historical archive', source_id='GLD holdings',
                url=gld_meta.get('requested_url', 'https://www.spdrgoldshares.com/usa/gld/'), unit='tonnes',
                frequency='D', timezone_name='NYSE date', date_column='date')
        except Exception as exc:
            records['gld_holdings'] = {'status': 'failed', 'source': 'SPDR Gold Shares historical archive',
                'source_id': 'GLD holdings', 'url': 'https://www.spdrgoldshares.com/usa/gld/',
                'unit': 'tonnes', 'frequency': 'D', 'timezone': 'NYSE date', 'retrieved_at': None,
                'first_publication_unknown': True, 'first_observation': None, 'last_observation': None,
                'missing_rows': None,
                'error_type': type(exc).__name__, 'message': 'GLD archive unavailable or invalid'}

        if imports is not None:
            imports = Path(imports)
            policy = None
            fedwatch_status = None
            lower_key = C.FRED_SERIES['DFEDTARL'][0]
            upper_key = C.FRED_SERIES['DFEDTARU'][0]
            if lower_key in public_frames and upper_key in public_frames:
                lower_df = public_frames[lower_key][['observation_date', 'value']].rename(
                    columns={'observation_date': 'date', 'value': 'lower_bp'})
                upper_df = public_frames[upper_key][['observation_date', 'value']].rename(
                    columns={'observation_date': 'date', 'value': 'upper_bp'})
                policy = lower_df.merge(upper_df, on='date', how='inner')
                policy[['lower_bp', 'upper_bp']] *= 100
            for path in imports.glob('*.csv'):
                m = re.fullmatch(r'fedwatch_(\d{8})\.csv', path.name)
                if path.name == 'etf_global.csv':
                    try:
                        etf_frame, etf_meta = _validated_etf_import(path, cutoff, sample_end)
                        local_frames['etf_global'] = etf_frame
                        (local_tmp / 'downloads' / 'imports').mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(path, local_tmp / 'downloads' / 'imports' / path.name)
                        records['etf_global'] = {'status': 'downloaded_local_only', 'source': 'World Gold Council',
                            'source_id': 'global gold ETF holdings/flows', 'unit': etf_meta['units'],
                            'frequency': etf_meta['frequency'], 'timezone': 'provider observation date',
                            'url': 'https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows',
                            'retrieved_at': datetime.now(UTC).isoformat(), 'first_publication_unknown': True,
                            **etf_meta}
                    except Exception as exc:
                        records['etf_global'] = {'status': 'failed', 'error_type': type(exc).__name__,
                                                 'message': 'ETF import invalid'}
                elif m:
                    key = f'fedwatch_{m.group(1)}'
                    try:
                        if policy is None:
                            raise ValueError('policy range unavailable')
                        (local_tmp / 'downloads' / 'imports').mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(path, local_tmp / 'downloads' / 'imports' / path.name)
                        meeting = f'{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}'
                        announcements = evidence_data.get('policy_announcements', [])
                        if not isinstance(announcements, list):
                            raise ValueError('policy_announcements must be a list')
                        announcement_days = set()
                        for item in announcements:
                            released_at = item.get('released_at')
                            if released_at:
                                released = pd.Timestamp(released_at)
                                if released.tzinfo is None:
                                    raise ValueError('policy announcement released_at must include timezone')
                                announcement_days.add(released.tz_convert(NY).date().isoformat())
                        announcement_dates = tuple(sorted(announcement_days))
                        normalized = normalize_fedwatch(pd.read_csv(path), meeting, cutoff, policy,
                                                        announcement_dates=announcement_dates)
                        normalized.to_csv(local_tmp / f'{key}.csv', index_label='date', lineterminator='\n')
                        records[key] = {'status': 'downloaded_local_only', 'source': 'CME FedWatch',
                            'source_id': meeting, 'unit': 'probability distribution; derived values in percent',
                            'frequency': 'D', 'url': 'https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html',
                            'retrieved_at': datetime.now(UTC).isoformat(), 'first_publication_unknown': True,
                            'missing_rows': int(normalized.isna().any(axis=1).sum())}
                        fedwatch_status = 'downloaded_local_only'
                    except Exception as exc:
                        records[key] = {'status': 'failed', 'source': 'CME FedWatch', 'error_type': type(exc).__name__,
                                        'message': 'FedWatch import unavailable or invalid'}
                        fedwatch_status = 'failed'
                else:
                    key = f'import_{path.stem}'
                    records[key] = {'status': 'failed', 'error_type': 'ValueError',
                                    'message': 'CSV import filename is not allowed'}
            if fedwatch_status:
                records['policy_expectations'] = {'status': fedwatch_status, 'source': 'CME FedWatch',
                    'source_id': 'meeting-specific distribution', 'message': 'distribution retained in local storage'}
        for name in ('policy_expectations', 'etf_global'):
            if name not in records:
                source_evidence = evidence_data.get('sources', {}).get(name)
                monthly_only = name == 'etf_global' and bool(source_evidence)
                records[name] = {'status': 'monthly_commentary_only' if monthly_only else 'missing',
                                 'source': 'CME FedWatch' if name == 'policy_expectations' else 'World Gold Council',
                                 'source_id': name, 'evidence': source_evidence,
                                 'frequency': 'M' if monthly_only else None,
                                 'last_observation': source_evidence.get('last_observation') if monthly_only and isinstance(source_evidence, dict) else None,
                                 'message': 'no validated distribution imported' if name == 'policy_expectations' else
                                            'commentary evidence only; no complete time series'}
        records['comex_activity'] = {'status': 'gap', 'source': 'CME', 'source_id': 'COMEX Gold volume/open interest',
                                     'url': 'https://www.cmegroup.com/markets/metals/precious/gold.volume.html',
                                     'unit': 'contracts', 'frequency': 'D', 'timezone': None,
                                     'first_publication_unknown': True, 'missing_rows': None,
                                     'message': 'Yahoo volume is not CME total volume or open interest'}

        for name, frame in public_frames.items():
            frame.to_csv(public_tmp / f'{name}.csv', index=False, lineterminator='\n')
            frame.to_csv(local_tmp / f'{name}.csv', index=False, lineterminator='\n')
            records.setdefault(name, {})

        revision_rows = []
        comparison = evidence_data.get('comparison_snapshot')
        if comparison:
            comparison_relative = _safe_relative(comparison)
            old_path = C.ROOT.joinpath(*comparison_relative.parts)
            try:
                _inside(old_path, C.ROOT)
                verify_snapshot(old_path)
                old_vintage = json.loads((old_path / 'manifest.json').read_text(encoding='utf-8')).get('cutoff_at')
                for name, new_frame in public_frames.items():
                    old_csv = old_path / f'{name}.csv'
                    if not old_csv.is_file():
                        revision_rows.append({'series': name, 'status': 'no_old_csv',
                            'old_vintage': old_vintage, 'new_vintage': records.get(name, {}).get('fred_vintage_date')})
                        continue
                    old_frame = pd.read_csv(old_csv)
                    joined = old_frame[['observation_date', 'value']].merge(
                        new_frame[['observation_date', 'value']], on='observation_date', how='inner',
                        suffixes=('_old', '_new'))
                    if joined.empty:
                        revision_rows.append({'series': name, 'status': 'no_common_dates',
                            'old_vintage': old_vintage, 'new_vintage': records.get(name, {}).get('fred_vintage_date')})
                    else:
                        for row in joined.itertuples(index=False):
                            revision_rows.append({'series': name, 'status': 'compared',
                                'old_vintage': old_vintage, 'new_vintage': records.get(name, {}).get('fred_vintage_date'),
                                'observation_date': row.observation_date, 'old_value': row.value_old, 'new_value': row.value_new})
            except Exception:
                revision_rows.append({'series': '*', 'status': 'old_snapshot_unavailable',
                                      'old_vintage': None, 'new_vintage': None})
        else:
            revision_rows.append({'series': '*', 'status': 'no_comparison_snapshot',
                                  'old_vintage': None, 'new_vintage': None})
        pd.DataFrame(revision_rows, columns=['series', 'status', 'old_vintage', 'new_vintage',
                    'observation_date', 'old_value', 'new_value']).to_csv(
                        public_tmp / 'revision-audit.csv', index=False, lineterminator='\n')
        for name, frame in local_frames.items():
            frame.to_csv(local_tmp / f'{name}.csv', index=False, lineterminator='\n')
        for name in local_frames:
            if name not in records:
                records[name] = {'status': 'downloaded_local_only'}

        daily_gap_rows = []
        for name, record in records.items():
            if record.get('status') in {'failed', 'gap', 'missing'}:
                daily_gap_rows.append({'series': name, 'status': record['status'],
                                       'error_type': record.get('error_type', ''),
                                       'message': record.get('message', '')})
        coverage_rows = [{'series': name, **{k: v for k, v in record.items() if k not in {'evidence'}}}
                         for name, record in sorted(records.items())]
        pd.DataFrame(coverage_rows).to_csv(public_tmp / 'coverage.csv', index=False, lineterminator='\n')
        _write_json(public_tmp / 'sources-evidence.json', evidence_data)
        readiness = {'primary_ready': bool(primary_check['ready']), 'primary_daily': primary_check,
                     'daily_date_set_gaps': gaps, 'weekday_missing_pending_calendar_review': pending,
                     'five_minute_required': False,
                     'five_minute_status': records.get('primary_intraday', {}).get('status', 'not_requested'),
                     'phase_1_authorized': False}
        _write_json(public_tmp / 'readiness.json', readiness)

        local_files = {p.relative_to(local_tmp).as_posix(): _digest(p)
                       for p in sorted(local_tmp.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
        local_manifest = {'cutoff_at': cutoff.astimezone(UTC).isoformat(), 'run_relative': relative.as_posix(),
                          'files': local_files}
        _write_json(local_tmp / 'manifest.json', local_manifest)
        public_files = {p.name: _digest(p) for p in sorted(public_tmp.iterdir()) if p.is_file() and p.name != 'manifest.json'}
        public_manifest = {'kind': 'gold-research-refresh', 'cutoff_at': cutoff.astimezone(UTC).isoformat(), 'focus_start': focus_start,
            'background_start': background_start, 'sample_end': sample_end, 'primary_ready': readiness['primary_ready'],
            'phase_1_authorized': False, 'local_manifest_sha256': _digest(local_tmp / 'manifest.json'),
            'local_run_relative': relative.as_posix(), 'files': public_files,
            'series': records, 'created_at': datetime.now(UTC).isoformat()}
        _write_json(public_tmp / 'manifest.json', public_manifest)
        public_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_tmp.rename(local_target)
        public_tmp.rename(public_target)
        return public_target
    except Exception:
        shutil.rmtree(public_tmp, ignore_errors=True)
        shutil.rmtree(local_tmp, ignore_errors=True)
        raise


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {'', '.', '..'} for part in path.parts):
        raise ValueError('manifest 含非法相对路径')
    return path


def _inside(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError('manifest 路径解析后越过run目录') from exc


def verify_refresh(public_path: Path, local_root: Path) -> dict:
    public_path, local_root = Path(public_path), Path(local_root)
    public_manifest_path = public_path / 'manifest.json'
    manifest = json.loads(public_manifest_path.read_text(encoding='utf-8'))
    if manifest.get('kind') != 'gold-research-refresh':
        raise ValueError('public manifest kind 不匹配')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('public manifest 缺少文件哈希')
    expected_names = set(files) | {'manifest.json'}
    actual_names = {p.relative_to(public_path).as_posix() for p in public_path.rglob('*') if p.is_file()}
    if actual_names != expected_names:
        raise ValueError('public run 文件集与 manifest 不一致')
    for name, digest in files.items():
        relative = _safe_relative(name)
        if len(relative.parts) != 1:
            raise ValueError('public manifest 路径必须是文件名')
        path = public_path / relative.as_posix()
        _inside(path, public_path)
        if _digest(path) != digest:
            raise ValueError(f'public 文件哈希不匹配: {name}')
    local_relative = _safe_relative(manifest.get('local_run_relative', ''))
    expected_prefix = PurePosixPath('runs')
    if local_relative.parts[:1] != expected_prefix.parts:
        raise ValueError('local_run_relative 必须位于 runs 下')
    local_path = local_root.joinpath(*local_relative.parts)
    _inside(local_path, local_root)
    local_manifest_path = local_path / 'manifest.json'
    if _digest(local_manifest_path) != manifest.get('local_manifest_sha256'):
        raise ValueError('local manifest 哈希不匹配')
    local_manifest = json.loads(local_manifest_path.read_text(encoding='utf-8'))
    local_files = local_manifest.get('files')
    if not isinstance(local_files, dict):
        raise ValueError('local manifest 缺少文件哈希')
    expected_local = set(local_files) | {'manifest.json'}
    actual_local = {p.relative_to(local_path).as_posix() for p in local_path.rglob('*') if p.is_file()}
    if actual_local != expected_local:
        raise ValueError('local run 文件集与 manifest 不一致')
    for name, digest in local_files.items():
        relative = _safe_relative(name)
        path = local_path.joinpath(*relative.parts)
        _inside(path, local_path)
        if _digest(path) != digest:
            raise ValueError(f'local 文件哈希不匹配: {name}')
    return manifest
