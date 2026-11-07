import json
import runpy
import sys
from pathlib import Path

import pytest

from inv import config as C


@pytest.mark.parametrize(('ready', 'expected'), [(True, 0), (False, 1)])
def test_research_update_reports_readiness_and_returns_matching_status(monkeypatch, tmp_path, capsys, ready, expected):
    root = tmp_path / 'repo'
    public_root = root / 'data/raw/gold-outlook'
    local_root = root / 'data/local/gold-outlook'
    monkeypatch.setattr(C, 'ROOT', root)
    monkeypatch.setattr(C, 'GOLD_RESEARCH_RAW', public_root)
    monkeypatch.setattr(C, 'GOLD_RESEARCH_LOCAL', local_root)
    run_path = public_root / 'runs/20261010T120000Z'

    def freeze(*args, **kwargs):
        run_path.mkdir(parents=True)
        (run_path / 'readiness.json').write_text(json.dumps({'primary_ready': ready}))
        return run_path

    monkeypatch.setattr('inv.gold_refresh.freeze_refresh', freeze)
    evidence = tmp_path / 'evidence.json'
    evidence.write_text('{}')
    monkeypatch.setattr(sys, 'argv', ['update_gold.py', '--research-update', '--cutoff',
        '2026-10-10T12:00:00Z', '--start', '2026-08-01', '--sample-end', '2026-10-09',
        '--evidence', str(evidence), '--refresh'])
    namespace = runpy.run_path(str(Path(__file__).parents[2] / 'scripts/update_gold.py'),
                               run_name='update_gold_cli_test')
    assert namespace['main']() == expected
    output = capsys.readouterr().out
    assert f'primary_ready={str(ready).lower()}' in output
    assert run_path.exists()
    assert json.loads((run_path / 'readiness.json').read_text())['primary_ready'] is ready
