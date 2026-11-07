import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from inv import config as C
from inv.gold_data import NORMAL_COLUMNS
from inv.gold_refresh import freeze_refresh, verify_refresh

CUTOFF = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)


def daily_frame(rows):
    return pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])


def setup_sources(monkeypatch, tmp_path, *, missing_endpoint=False, missing_price=False,
                  missing_volume=False, mismatch_dates=False, intraday_error=False):
    def yahoo(symbol, interval, start, cutoff):
        if interval == '5m':
            if intraday_error:
                raise ValueError('vendor body secret')
            frame = pd.DataFrame({'timestamp': ['2026-09-09T20:45:00Z', '2026-09-09T20:55:00Z', '2026-09-09T21:00:00Z'],
                'open': [2500, 2501, 2502], 'high': [2502, 2503, 2504], 'low': [2499, 2500, 2501],
                'close': [2501, 2502, 2503], 'volume': [10, 12, 14]})
            granularity = '5m'
        else:
            rows = [['2026-07-31', 2300, 2310, 2290, 2305, 5],
                    ['2026-08-31', 2400, 2410, 2390, 2405, 10],
                    ['2026-09-08', 2500, 2510, 2490, 2505, 20],
                    ['2026-09-09', 2510, 2520, 2500, 2515, 30]]
            if symbol == 'GCZ26.CMX' and mismatch_dates:
                rows = [rows[0], rows[1], rows[3]]
            if symbol == 'GCZ26.CMX' and missing_endpoint:
                rows = rows[:3]
            if symbol == 'GCZ26.CMX' and missing_price:
                rows[1][4] = None
            if symbol == 'GCZ26.CMX' and missing_volume:
                rows[3][5] = None
            frame = daily_frame(rows)
            granularity = '1d'
        return frame, {'source': 'Yahoo Chart API', 'symbol': symbol, 'currency': 'USD',
            'instrumentType': 'FUTURE' if symbol != 'DX-Y.NYB' else 'INDEX',
            'exchangeTimezoneName': 'America/Chicago', 'dataGranularity': granularity,
            'retrieved_at': '2026-09-10T22:00:00+00:00', 'raw_response': {'chart': {'result': []}}}

    def government(cutoff, background_start, focus_start, download_dir, release_times):
        download_dir.mkdir(parents=True, exist_ok=True)
        (download_dir / 'fred-response.json').write_text('{"safe": true}')
        frame = pd.DataFrame([['2026-09-08', 4.1, '', '2026-09-09T05:00:00Z', '2026-09-09'],
                              ['2026-09-09', None, '', '2026-09-10T05:00:00Z', '2026-09-09']],
                             columns=NORMAL_COLUMNS)
        frames = {'ust2y': frame}
        for series_id, value in [('DFEDTARL', 3.5), ('DFEDTARU', 3.75)]:
            frames[C.FRED_SERIES[series_id][0]] = pd.DataFrame(
                [['2026-09-08', value, '', '2026-09-09T05:00:00Z', '2026-09-09']], columns=NORMAL_COLUMNS)
        records = {'ust2y': {'status': 'downloaded', 'provider': 'FRED/ALFRED',
            'source_id': 'DGS2', 'unit': '%', 'frequency': 'D', 'timezone': 'America/Chicago',
            'source_url': 'https://fred.stlouisfed.org/series/DGS2', 'retrieved_at': '2026-09-10T22:00Z',
            'first_publication_unknown': True, 'fred_vintage_date': '2026-09-09', 'missing_observations': 1}}
        return frames, records

    def gld(start, cutoff, download_dir):
        download_dir.mkdir(parents=True, exist_ok=True)
        (download_dir / 'spdr-gld-historical-archive.xlsx').write_bytes(b'local workbook')
        return pd.DataFrame([{'date': '2026-09-08', 'tonnes': 1000.0, 'holiday': False}]), {
            'source_url': 'https://www.spdrgoldshares.com/usa/gld/', 'retrieved_at': '2026-09-10T22:00Z'}

    monkeypatch.setattr('inv.gold_refresh.fetch_yahoo', yahoo)
    monkeypatch.setattr('inv.gold_refresh.fetch_government', government)
    monkeypatch.setattr('inv.gold_refresh.fetch_gld', gld)


def run(tmp_path, monkeypatch, *, focus_start='2026-08-01', **kwargs):
    setup_sources(monkeypatch, tmp_path, **kwargs)
    evidence = tmp_path / 'evidence.json'
    evidence.write_text(json.dumps({'sources': {'etf_global': {'status': 'monthly_commentary_only'}},
                                   'limitations': ['older raw cache metadata unavailable'],
                                   'cftc_release_times': {'2026-09-01': '2026-09-04T15:30:00-04:00'}}))
    return freeze_refresh(CUTOFF, focus_start=focus_start, background_start='2023-08-01',
        sample_end='2026-09-09', refresh=True, public_root=tmp_path / 'public',
        local_root=tmp_path / 'local', evidence=evidence)


def test_immutable_run_and_public_commercial_boundary(monkeypatch, tmp_path):
    path = run(tmp_path, monkeypatch)
    manifest = verify_refresh(path, tmp_path / 'local')
    assert manifest['primary_ready'] is True
    assert 'primary_daily.csv' not in manifest['files']
    assert 'primary_intraday.csv' not in manifest['files']
    assert 'gld_holdings.csv' not in manifest['files']
    assert 'ust2y.csv' in manifest['files']
    assert (path / 'sources-evidence.json').exists()
    assert (tmp_path / 'local/runs/20260910T220000Z/price_checks.csv').exists()
    assert (tmp_path / 'local/runs/20260910T220000Z/downloads/spdr-gld-historical-archive.xlsx').exists()
    assert manifest['series']['primary_intraday']['last_bar_end'] == '2026-09-09T21:00:00+00:00'
    assert manifest['series']['primary_intraday']['gap_count'] == 1
    assert manifest['series']['ust2y']['last_observation'] == '2026-09-08'
    assert manifest['series']['ust2y']['last_row_date'] == '2026-09-09'
    assert manifest['series']['ust2y']['rows'] == 2
    assert manifest['series']['ust2y']['valid_rows'] == 1
    with pytest.raises(ValueError, match='已存在'):
        run(tmp_path, monkeypatch)


@pytest.mark.parametrize('kwargs', [{'missing_endpoint': True}, {'missing_price': True}, {'mismatch_dates': True}])
def test_readiness_false_for_endpoint_missing_price_or_history_gap(monkeypatch, tmp_path, kwargs):
    path = run(tmp_path, monkeypatch, **kwargs)
    manifest = verify_refresh(path, tmp_path / 'local')
    assert manifest['primary_ready'] is False
    readiness = json.loads((path / 'readiness.json').read_text())
    if kwargs.get('mismatch_dates'):
        assert readiness['daily_date_set_gaps']['primary_missing_from_history'] == ['2026-09-08']


def test_failed_intraday_is_only_a_supporting_gap_and_records_do_not_echo_vendor(monkeypatch, tmp_path):
    path = run(tmp_path, monkeypatch, intraday_error=True)
    manifest = verify_refresh(path, tmp_path / 'local')
    assert manifest['primary_ready'] is True
    assert manifest['series']['primary_intraday']['status'] == 'gap'
    assert 'vendor body secret' not in (path / 'coverage.csv').read_text()


def test_missing_volume_is_a_gap_but_does_not_block_close_readiness(monkeypatch, tmp_path):
    path = run(tmp_path, monkeypatch, missing_volume=True)
    manifest = verify_refresh(path, tmp_path / 'local')
    assert manifest['primary_ready'] is True
    assert manifest['series']['primary_daily']['missing_rows'] == 1
    assert manifest['series']['primary_daily']['last_observation'] == '2026-09-09'
    assert manifest['series']['primary_daily']['last_row_date'] == '2026-09-09'


@pytest.mark.parametrize('focus_start', ['2026-09-01', '2026-07-01'])
def test_refresh_accepts_parameterized_focus_start(monkeypatch, tmp_path, focus_start):
    path = run(tmp_path, monkeypatch, focus_start=focus_start)
    manifest = verify_refresh(path, tmp_path / 'local')
    assert manifest['focus_start'] == focus_start


def test_detects_public_and_local_hash_tampering(monkeypatch, tmp_path):
    path = run(tmp_path, monkeypatch)
    (path / 'ust2y.csv').write_text('tampered')
    with pytest.raises(ValueError, match='哈希不匹配'):
        verify_refresh(path, tmp_path / 'local')


def test_detects_local_hash_tampering(monkeypatch, tmp_path):
    path = run(tmp_path, monkeypatch)
    (tmp_path / 'local/runs/20260910T220000Z/primary_daily.csv').write_text('tampered')
    with pytest.raises(ValueError, match='哈希不匹配'):
        verify_refresh(path, tmp_path / 'local')


def test_local_run_is_retained_if_public_rename_fails(monkeypatch, tmp_path):
    setup_sources(monkeypatch, tmp_path)
    evidence = tmp_path / 'evidence.json'
    evidence.write_text('{}')
    public_stage = tmp_path / 'public/runs/20260910T220000Z.tmp'
    original_rename = Path.rename
    def fail_public_stage(self, target):
        if self == public_stage:
            raise OSError('public rename failure')
        return original_rename(self, target)
    monkeypatch.setattr(Path, 'rename', fail_public_stage)
    with pytest.raises(OSError, match='public rename failure'):
        freeze_refresh(CUTOFF, focus_start='2026-08-01', background_start='2023-08-01',
            sample_end='2026-09-09', refresh=True, public_root=tmp_path / 'public',
            local_root=tmp_path / 'local', evidence=evidence)
    assert (tmp_path / 'local/runs/20260910T220000Z/manifest.json').exists()
    assert not (tmp_path / 'public/runs/20260910T220000Z').exists()
    assert not public_stage.exists()


def test_rejects_unsafe_local_relative_path(monkeypatch, tmp_path):
    path = run(tmp_path, monkeypatch)
    manifest_path = path / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['local_run_relative'] = 'runs/../../outside'
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='非法相对路径'):
        verify_refresh(path, tmp_path / 'local')


def test_imported_fedwatch_and_etf_remain_local_and_use_observed_policy(monkeypatch, tmp_path):
    setup_sources(monkeypatch, tmp_path)
    captured = {}
    def normalize(frame, meeting, cutoff, policy, *, announcement_dates=()):
        captured['meeting'] = meeting
        captured['policy'] = policy.copy()
        captured['announcement_dates'] = announcement_dates
        return pd.DataFrame({'higher_pct': [35]}, index=pd.DatetimeIndex(['2026-09-08'], name='date'))
    monkeypatch.setattr('inv.gold_refresh.normalize_fedwatch', normalize)
    evidence = tmp_path / 'evidence.json'
    evidence.write_text(json.dumps({'policy_announcements': [
        {'released_at': '2026-09-16T14:00:00-04:00'}, {'released_at': '2026-09-16T02:00:00Z'}]}))
    imports = tmp_path / 'imports'
    imports.mkdir()
    (imports / 'fedwatch_20260916.csv').write_text('Date,"(350-375)","(375-400)"\n09/08/2026,0.65,0.35\n')
    (imports / 'etf_global.csv').write_text(
        'observation_date,known_by_at,holdings_tonnes\n2026-09-01,2026-09-02T00:00:00Z,1000\n')
    path = freeze_refresh(CUTOFF, focus_start='2026-08-01', background_start='2023-08-01',
        sample_end='2026-09-09', refresh=True, public_root=tmp_path / 'public', local_root=tmp_path / 'local',
        evidence=evidence, imports=imports)
    manifest = verify_refresh(path, tmp_path / 'local')
    local = tmp_path / 'local/runs/20260910T220000Z'
    assert captured['meeting'] == '2026-09-16'
    assert captured['policy'][['lower_bp', 'upper_bp']].iloc[0].tolist() == [350, 375]
    assert captured['announcement_dates'] == ('2026-09-15', '2026-09-16')
    assert (local / 'downloads/imports/fedwatch_20260916.csv').exists()
    assert (local / 'downloads/imports/etf_global.csv').exists()
    assert 'fedwatch_20260916.csv' not in manifest['files']
    assert 'etf_global.csv' not in manifest['files']
    assert manifest['series']['policy_expectations']['status'] == 'downloaded_local_only'


def test_revision_audit_compares_only_common_public_government_values(monkeypatch, tmp_path):
    setup_sources(monkeypatch, tmp_path)
    repository = tmp_path / 'repo'
    old = repository / 'data/raw/gold-outlook/phase4/snapshots/20260911T102805Z'
    old.mkdir(parents=True)
    old_csv = old / 'ust2y.csv'
    pd.DataFrame([['2026-09-08', 4.0, '', '', '2026-09-10']], columns=NORMAL_COLUMNS).to_csv(old_csv, index=False)
    (old / 'manifest.json').write_text(json.dumps({'cutoff_at': '2026-09-11T10:28:05Z',
        'files': {'ust2y.csv': hashlib.sha256(old_csv.read_bytes()).hexdigest()}}))
    monkeypatch.setattr('inv.gold_refresh.C.ROOT', repository)
    evidence = tmp_path / 'evidence.json'
    evidence.write_text(json.dumps({'comparison_snapshot': 'data/raw/gold-outlook/phase4/snapshots/20260911T102805Z'}))
    path = freeze_refresh(CUTOFF, focus_start='2026-08-01', background_start='2023-08-01',
        sample_end='2026-09-09', refresh=True, public_root=tmp_path / 'public', local_root=tmp_path / 'local',
        evidence=evidence)
    manifest = verify_refresh(path, tmp_path / 'local')
    assert manifest['local_run_relative'] == 'runs/20260910T220000Z'
    audit = pd.read_csv(path / 'revision-audit.csv')
    row = audit.loc[audit.series.eq('ust2y')].iloc[0]
    assert row.status == 'compared'
    assert row.old_value == 4.0 and row.new_value == 4.1
    assert (audit.status == 'no_old_csv').any()


def test_supporting_source_directory_is_copied_and_hashed(monkeypatch, tmp_path):
    setup_sources(monkeypatch, tmp_path)
    evidence = tmp_path / 'evidence.json'
    evidence.write_text('{}')
    local_root = tmp_path / 'local'
    support = local_root / 'source-downloads/20261008'
    support.mkdir(parents=True)
    (support / 'official-event.html').write_text('<html>source evidence</html>')
    evidence.write_text(json.dumps({'supporting_local_directory': 'source-downloads/20261008'}))
    path = freeze_refresh(CUTOFF, focus_start='2026-08-01', background_start='2023-08-01',
        sample_end='2026-09-09', refresh=True, public_root=tmp_path / 'public',
        local_root=local_root, evidence=evidence)
    verify_refresh(path, local_root)
    local_manifest = json.loads((local_root / 'runs/20260910T220000Z/manifest.json').read_text())
    assert 'downloads/support/official-event.html' in local_manifest['files']


def test_missing_supporting_directory_is_rejected_and_staging_removed(monkeypatch, tmp_path):
    setup_sources(monkeypatch, tmp_path)
    evidence = tmp_path / 'evidence.json'
    evidence.write_text(json.dumps({'supporting_local_directory': 'source-downloads/missing'}))
    with pytest.raises(ValueError, match='不存在'):
        freeze_refresh(CUTOFF, focus_start='2026-08-01', background_start='2023-08-01',
            sample_end='2026-09-09', refresh=True, public_root=tmp_path / 'public',
            local_root=tmp_path / 'local', evidence=evidence)
    assert not (tmp_path / 'public/runs/20260910T220000Z.tmp').exists()
    assert not (tmp_path / 'local/runs/20260910T220000Z.tmp').exists()


def test_refresh_false_and_same_day_cutoff_sample_are_rejected(tmp_path):
    evidence = tmp_path / 'evidence.json'
    evidence.write_text('{}')
    args = dict(focus_start='2026-08-01', background_start='2023-08-01', sample_end='2026-09-09',
                public_root=tmp_path / 'public', local_root=tmp_path / 'local', evidence=evidence)
    with pytest.raises(ValueError, match='refresh=True'):
        freeze_refresh(CUTOFF, refresh=False, **args)
    with pytest.raises(ValueError, match='早于 cutoff'):
        freeze_refresh(CUTOFF, sample_end='2026-09-10', refresh=True, **{k: v for k, v in args.items() if k != 'sample_end'})
