"""Offline mechanical verification for the frozen 2026-10-08 gold refresh.

Run from any directory with the repository's Python environment:
    .venv/bin/python data/raw/gold-outlook/reviews/verify-refresh-20261008.py

The profile contains no commercial price values or raw commercial observations.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'src'))

from inv.gold_data import verify_snapshot  # noqa: E402
from inv.gold_intraday import FIELDS as INTRADAY_FIELDS  # noqa: E402
from inv.gold_intraday import regular_session  # noqa: E402
from inv.gold_refresh import verify_refresh  # noqa: E402

RUN_ID = '20261008T090303Z'
OLD_PHASE4_ID = '20260911T102805Z'
PHASE0_ID = '20260909T115946Z'
DATA = ROOT / 'data/raw/gold-outlook'
PUBLIC_RUN = DATA / 'runs' / RUN_ID
LOCAL_ROOT = ROOT / 'data/local/gold-outlook'
PHASE4 = DATA / 'phase4/snapshots' / OLD_PHASE4_ID
PHASE0 = DATA / 'snapshots' / PHASE0_ID
LOCAL_RUN = LOCAL_ROOT / 'runs' / RUN_ID
PROFILE_PATH = DATA / 'reviews/refresh-20261008-profile.json'
VALUE_FIELDS = {
    'FRED/ALFRED': ('value',),
    'FRED': ('value',),
    'CFTC': ('value', 'managed_money_long', 'managed_money_short',
             'managed_money_spreading', 'open_interest'),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def clean_value(value: object) -> float | None:
    if pd.isna(value):
        return None
    number = float(value)
    return number if np.isfinite(number) else None


def csv_vintages(frame: pd.DataFrame) -> dict:
    if 'vintage_date' not in frame:
        return {'status': 'column_missing', 'dates': []}
    dates = sorted({str(v).strip() for v in frame.vintage_date.dropna() if str(v).strip()})
    return {'status': 'recorded' if dates else 'empty_in_csv', 'dates': dates}


def compare_government(run_manifest: dict) -> dict:
    series = run_manifest.get('series', {})
    results = {}
    for name, metadata in sorted(series.items()):
        if metadata.get('source') not in {'FRED/ALFRED', 'FRED', 'CFTC'}:
            continue
        current_path = PUBLIC_RUN / f'{name}.csv'
        result = {
            'source': metadata.get('source'),
            'source_id': metadata.get('source_id'),
            'current_csv': rel(current_path) if current_path.is_file() else None,
            'current_csv_sha256': digest(current_path) if current_path.is_file() else None,
            'csv_vintage_date': {'status': 'unavailable', 'dates': []},
            'reference': None,
            'common_date_count': 0,
            'changed_value_count': 0,
            'missing_status_change_count': 0,
            'value_changes': [],
            'missing_status_changes': [],
        }
        if not current_path.is_file():
            result['status'] = 'current_csv_missing'
            results[name] = result
            continue
        current = pd.read_csv(current_path)
        result['csv_vintage_date'] = csv_vintages(current)
        if 'observation_date' not in current:
            result['status'] = 'current_date_column_missing'
            results[name] = result
            continue
        current['observation_date'] = current.observation_date.astype(str)
        if current.observation_date.duplicated().any():
            raise ValueError(f'{name} 当前政府 CSV 的观测日期重复')
        ref_path = PHASE4 / f'{name}.csv'
        ref_label = 'phase4'
        if not ref_path.is_file():
            ref_path = PHASE0 / f'{name}.csv'
            ref_label = 'phase0'
        if not ref_path.is_file():
            result.update({'status': 'reference_csv_missing', 'reference': {'snapshot': ref_label}})
            results[name] = result
            continue
        reference = pd.read_csv(ref_path)
        result['reference'] = {
            'snapshot': ref_label,
            'csv': rel(ref_path),
            'csv_sha256': digest(ref_path),
            'csv_vintage_date': csv_vintages(reference),
        }
        if 'observation_date' not in reference:
            result.update({'status': 'reference_date_column_missing'})
            results[name] = result
            continue
        reference['observation_date'] = reference.observation_date.astype(str)
        if reference.observation_date.duplicated().any():
            raise ValueError(f'{name} 参考政府 CSV 的观测日期重复')
        expected_fields = VALUE_FIELDS.get(metadata.get('source'), ('value',))
        comparable_fields = [field for field in expected_fields
                             if field in current.columns and field in reference.columns]
        for field in comparable_fields:
            current[field] = pd.to_numeric(current[field], errors='raise')
            reference[field] = pd.to_numeric(reference[field], errors='raise')
        missing_fields = [field for field in expected_fields
                          if field not in current.columns or field not in reference.columns]
        current_by_date = current.set_index('observation_date')
        reference_by_date = reference.set_index('observation_date')
        common_dates = current_by_date.index.intersection(reference_by_date.index).sort_values()
        result['common_date_count'] = len(common_dates)
        for observation_date in common_dates:
            for field in comparable_fields:
                old_value = reference_by_date.at[observation_date, field]
                new_value = current_by_date.at[observation_date, field]
                old_missing, new_missing = bool(pd.isna(old_value)), bool(pd.isna(new_value))
                if old_missing != new_missing:
                    result['missing_status_changes'].append({
                        'date': observation_date, 'field': field,
                        'reference_missing': old_missing, 'current_missing': new_missing,
                    })
                elif not old_missing and not np.isclose(float(old_value), float(new_value), atol=0, rtol=0):
                    result['value_changes'].append({
                        'date': observation_date, 'field': field,
                        'reference_value': clean_value(old_value), 'current_value': clean_value(new_value),
                    })
        result.update({
            'status': 'compared',
            'comparable_value_fields': comparable_fields,
            'expected_value_fields_missing_from_one_or_both_csvs': missing_fields,
            'changed_value_count': len(result['value_changes']),
            'missing_status_change_count': len(result['missing_status_changes']),
        })
        results[name] = result
    return results


def profile_primary(run_manifest: dict) -> dict:
    path = LOCAL_RUN / 'primary_daily.csv'
    frame = pd.read_csv(path)
    frame['date'] = pd.to_datetime(frame.date, format='%Y-%m-%d', errors='raise')
    if frame.date.duplicated().any():
        unique = False
    else:
        unique = True
    focus_start = pd.Timestamp(run_manifest['focus_start'])
    sample_end = pd.Timestamp(run_manifest['sample_end'])
    focus = frame.loc[frame.date.between(focus_start, sample_end)].copy()
    ohlc_fields = ['open', 'high', 'low', 'close']
    complete = focus[ohlc_fields].notna().all(axis=1)
    valid = focus.loc[complete]
    readiness_path = PUBLIC_RUN / 'readiness.json'
    readiness = json.loads(readiness_path.read_text(encoding='utf-8'))
    baseline = readiness['primary_daily']['baseline_date']
    baseline_rows = frame.loc[frame.date.eq(pd.Timestamp(baseline))]
    if valid.empty:
        high_dates, close_dates = [], []
    else:
        high_dates = valid.loc[valid.high.eq(valid.high.max()), 'date'].dt.strftime('%Y-%m-%d').tolist()
        close_dates = valid.loc[valid.close.eq(valid.close.max()), 'date'].dt.strftime('%Y-%m-%d').tolist()
    return {
        'source_file': rel(path),
        'date_unique': unique,
        'row_count': len(frame),
        'date_endpoints': {
            'first': frame.date.min().strftime('%Y-%m-%d') if len(frame) else None,
            'last': frame.date.max().strftime('%Y-%m-%d') if len(frame) else None,
        },
        'focus_window': {'start': focus_start.strftime('%Y-%m-%d'), 'end': sample_end.strftime('%Y-%m-%d'),
                         'rows': len(focus), 'complete_ohlc_rows': int(complete.sum()),
                         'incomplete_ohlc_dates': focus.loc[~complete, 'date'].dt.strftime('%Y-%m-%d').tolist()},
        'baseline_date': baseline,
        'baseline_present': len(baseline_rows) == 1,
        'baseline_ohlc_complete': bool(len(baseline_rows) == 1 and baseline_rows[ohlc_fields].notna().all(axis=None)),
        'focus_max_high_dates': high_dates,
        'focus_max_close_dates': close_dates,
    }


def profile_intraday() -> dict:
    path = LOCAL_RUN / 'primary_intraday.csv'
    frame = pd.read_csv(path)
    index = pd.DatetimeIndex(pd.to_datetime(frame.timestamp, utc=True, errors='raise'))
    values = frame[INTRADAY_FIELDS].apply(pd.to_numeric, errors='raise')
    all_missing = values.isna().all(axis=1).to_numpy()
    any_missing = values.isna().any(axis=1).to_numpy()
    partial_missing = any_missing & ~all_missing
    in_session = regular_session(index)
    nonempty_outside = values.notna().any(axis=1).to_numpy() & ~in_session
    return {
        'source_file': rel(path),
        'row_count': len(frame),
        'complete_empty_ohlcv_rows': int(all_missing.sum()),
        'partial_empty_ohlcv_rows': int(partial_missing.sum()),
        'missing_rows_by_regular_session': {
            'complete_empty_inside': int((all_missing & in_session).sum()),
            'complete_empty_outside': int((all_missing & ~in_session).sum()),
            'partial_empty_inside': int((partial_missing & in_session).sum()),
            'partial_empty_outside': int((partial_missing & ~in_session).sum()),
        },
        'nonempty_outside_regular_session_count': int(nonempty_outside.sum()),
        'nonempty_outside_regular_session_timestamps': index[nonempty_outside].strftime('%Y-%m-%dT%H:%M:%SZ').tolist(),
    }


def main() -> None:
    public_manifest = verify_refresh(PUBLIC_RUN, LOCAL_ROOT)
    local_run = LOCAL_ROOT.joinpath(*Path(public_manifest['local_run_relative']).parts)
    local_manifest_path = local_run / 'manifest.json'
    local_manifest = json.loads(local_manifest_path.read_text(encoding='utf-8'))
    phase4_manifest = verify_snapshot(PHASE4)
    phase0_manifest = verify_snapshot(PHASE0)
    report = {
        'run_id': RUN_ID,
        'verification': {
            'refresh': {'status': 'passed', 'path': rel(PUBLIC_RUN),
                        'public_file_count': len(public_manifest['files']) + 1,
                        'local_path': rel(local_run),
                        'local_file_count': len(local_manifest['files']) + 1,
                        'local_manifest_sha256': digest(local_manifest_path),
                        'local_manifest_sha256_matches_public': (
                            digest(local_manifest_path) == public_manifest['local_manifest_sha256']),
                        'local_manifest_file_entry_count': len(local_manifest['files'])},
            'old_phase4_snapshot': {'status': 'passed', 'path': rel(PHASE4),
                                    'phase': phase4_manifest.get('phase'),
                                    'file_count': len(phase4_manifest['files']) + 1},
            'phase0_snapshot': {'status': 'passed', 'path': rel(PHASE0),
                                'phase': phase0_manifest.get('phase'),
                                'file_count': len(phase0_manifest['files']) + 1},
        },
        'government_series_comparison': compare_government(public_manifest),
        'primary_daily': profile_primary(public_manifest),
        'primary_intraday': profile_intraday(),
    }
    PROFILE_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'profile': rel(PROFILE_PATH),
        'verification': report['verification'],
        'government_series_count': len(report['government_series_comparison']),
        'government_changed_values': sum(x['changed_value_count'] for x in report['government_series_comparison'].values()),
        'government_missing_status_changes': sum(x['missing_status_change_count'] for x in report['government_series_comparison'].values()),
        'primary_daily': report['primary_daily'],
        'primary_intraday': report['primary_intraday'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
