import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from inv import config as C
from inv.gold_data import NORMAL_COLUMNS
from inv.gold_refresh_government import fetch_government

CUTOFF = datetime(2026, 9, 9, 18, tzinfo=timezone.utc)


def fred_frame(value, *, missing=False):
    return pd.DataFrame([
        ['2023-07-31', value, '', '2023-08-01T05:00:00Z', '2026-09-08'],
        ['2023-08-01', np.nan if missing else value + 1, '', '2023-08-02T05:00:00Z', '2026-09-08'],
        ['2026-09-08', value + 2, '', '2026-09-09T05:00:00Z', '2026-09-08'],
        ['2026-09-10', value + 3, '', '2026-09-11T05:00:00Z', '2026-09-08'],
    ], columns=NORMAL_COLUMNS)


def write_cftc_archives(cache: Path, *, bad=False):
    columns = ['CFTC_Contract_Market_Code', 'Market_and_Exchange_Names', 'Report_Date_as_YYYY-MM-DD',
               'M_Money_Positions_Long_All', 'M_Money_Positions_Short_All',
               'M_Money_Positions_Spread_All', 'Open_Interest_All']
    rows = []
    def row(day, oi=300):
        return ['088691', 'GOLD - COMMODITY EXCHANGE INC.', day, 100, 40, 12, oi]
    for year in (2023, 2024, 2025):
        rows.append(row(f'{year}-08-01'))
    rows += [row('2026-06-30'), row('2026-07-07'), row('2026-09-01'),
             row('2026-09-08', oi=-1 if bad else 300), row('2026-09-10')]
    cache.mkdir(parents=True, exist_ok=True)
    for year in (2023, 2024, 2025, 2026):
        data = pd.DataFrame([r for r in rows if r[2].startswith(str(year))], columns=columns).to_csv(index=False)
        with zipfile.ZipFile(cache / f'cftc-{year}.zip', 'w') as archive:
            archive.writestr(f'f_year_{year}.txt', data)


def valid_calls(monkeypatch, *, bad_sid=None, bad_cftc=False):
    calls = []
    def fred(sid, cutoff, cache, *, refresh):
        calls.append((sid, cutoff, cache, refresh))
        if sid == bad_sid:
            raise RuntimeError('secret key=https://private.example')
        return fred_frame(len(calls), missing=(sid == C.GOLD_RESEARCH_FRED_IDS[0])), {
            'retrieved_at': '2026-09-09T18:00:00Z'}
    def cftc(cutoff, cache, releases, *, refresh):
        calls.append(('CFTC', cutoff, cache, refresh, releases))
        write_cftc_archives(cache, bad=bad_cftc)
        return pd.DataFrame(), {'retrieved_at': '2026-09-09T18:00:00Z',
                                'inputs': [{'file': f'cftc-{year}.zip', 'sha256': f'hash-{year}'}
                                           for year in (2023, 2024, 2025, 2026)]}
    monkeypatch.setattr('inv.gold_refresh_government.G.fred_snapshot', fred)
    monkeypatch.setattr('inv.gold_refresh_government.G.cftc_snapshot', cftc)
    return calls


def test_fetches_registered_series_preserves_gaps_and_does_not_align(monkeypatch, tmp_path):
    calls = valid_calls(monkeypatch)
    releases = {'2026-09-01': '2026-09-04T15:30:00-04:00'}
    frames, records = fetch_government(CUTOFF, '2023-08-01', '2026-08-01', tmp_path, releases)
    assert len(calls) == len(C.GOLD_RESEARCH_FRED_IDS) + 1
    assert all(call[3] is True for call in calls)
    assert calls[-1][4] == releases
    assert records['cot_gold']['status'] == 'downloaded', records['cot_gold'].get('message')
    assert set(frames) == {C.FRED_SERIES[sid][0] for sid in C.GOLD_RESEARCH_FRED_IDS} | {'cot_gold'}
    assert all(list(frames[C.FRED_SERIES[sid][0]].columns) == NORMAL_COLUMNS for sid in C.GOLD_RESEARCH_FRED_IDS)
    assert frames[C.FRED_SERIES[C.GOLD_RESEARCH_FRED_IDS[0]][0]].observation_date.tolist() == ['2023-08-01', '2026-09-08']
    assert frames[C.FRED_SERIES[C.GOLD_RESEARCH_FRED_IDS[0]] [0]].value.iloc[0] != frames[C.FRED_SERIES[C.GOLD_RESEARCH_FRED_IDS[1]][0]].value.iloc[0]
    assert records[C.FRED_SERIES[C.GOLD_RESEARCH_FRED_IDS[0]][0]]['missing_observations'] == 1
    assert records['cot_gold']['focus_rows'] == 1
    assert frames['cot_gold'].value.iloc[0] == 60


def test_fred_failure_isolated_and_message_does_not_leak(monkeypatch, tmp_path):
    failed_id = C.GOLD_RESEARCH_FRED_IDS[0]
    valid_calls(monkeypatch, bad_sid=failed_id)
    frames, records = fetch_government(CUTOFF, '2023-08-01', '2026-08-01', tmp_path, {})
    record = records[C.FRED_SERIES[failed_id][0]]
    assert record['status'] == 'failed'
    assert 'secret' not in str(record) and 'private.example' not in str(record)
    assert C.FRED_SERIES[failed_id][0] not in frames
    assert 'cot_gold' in frames


@pytest.mark.parametrize('background_start', ['2023-07-31', '2022-01-01'])
def test_background_start_cannot_precede_existing_source_limit(monkeypatch, tmp_path, background_start):
    valid_calls(monkeypatch)
    with pytest.raises(ValueError, match='不能早于 2023-08-01'):
        fetch_government(CUTOFF, background_start, '2026-08-01', tmp_path, {})


def test_cftc_wrong_net_marks_only_cftc_failed(monkeypatch, tmp_path):
    valid_calls(monkeypatch, bad_cftc=True)
    frames, records = fetch_government(CUTOFF, '2023-08-01', '2026-08-01', tmp_path,
        {'2026-09-08': '2026-09-09T10:00:00-04:00'})
    assert records['cot_gold']['status'] == 'failed'
    assert records['cot_gold']['message'] == 'CFTC series unavailable or invalid'
    assert 'cot_gold' not in frames
    assert len(frames) == len(C.GOLD_RESEARCH_FRED_IDS)


@pytest.mark.parametrize(('focus', 'expected_dates'), [
    ('2026-09-01', ['2023-08-01', '2024-08-01', '2025-08-01', '2026-06-30', '2026-07-07', '2026-09-01']),
    ('2026-07-01', ['2023-08-01', '2024-08-01', '2025-08-01', '2026-06-30', '2026-09-01']),
])
def test_cftc_uses_custom_focus_and_only_released_recent_reports(monkeypatch, tmp_path, focus, expected_dates):
    valid_calls(monkeypatch)
    releases = {'2026-09-01': '2026-09-04T15:30:00-04:00',
                '2026-09-08': '2026-09-11T15:30:00-04:00'}
    frames, _ = fetch_government(CUTOFF, '2023-08-01', focus, tmp_path, releases)
    cftc = frames['cot_gold']
    assert cftc.observation_date.tolist() == expected_dates
    assert cftc.loc[cftc.observation_date.eq('2026-06-30'), 'available_at'].iloc[0] == ''
    assert cftc.loc[cftc.observation_date.eq('2026-09-01'), 'available_at'].iloc[0] == releases['2026-09-01']
    assert '2026-09-08' not in cftc.observation_date.tolist()
