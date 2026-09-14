import hashlib
import json

import pandas as pd
import pytest

from inv.gold_analysis import interval_stats
from inv.gold_intraday import broken_line, load_intraday, normalize_bars


def raw(times, values=None):
    values = values or [100] * len(times)
    return pd.DataFrame({'Datetime': times, 'Open': values, 'High': [p + 1 for p in values],
                         'Low': [p - 1 for p in values], 'Close': values, 'Volume': 10})


def clean(frame, cutoff='2026-08-03T18:30:00-04:00'):
    return normalize_bars(frame, cutoff=cutoff, start='2026-08-03T18:00:00-04:00', end='2026-08-03T19:00:00-04:00')


def test_completed_bar_filter_and_missing_price_remain_gaps():
    data = raw(['2026-08-03T18:00:00-04:00', '2026-08-03T18:05:00-04:00', '2026-08-03T18:10:00-04:00',
                '2026-08-03T18:15:00-04:00'])
    data.loc[1, 'Close'] = float('nan')
    result, audit = clean(data, cutoff='2026-08-03T18:17:00-04:00')
    assert result.bar_end.tolist() == list(pd.to_datetime(['2026-08-03T22:05:00Z', '2026-08-03T22:15:00Z']))
    assert [r['reasons'] for r in audit['excluded']] == [['missing_ohlcv'], ['outside_completed_window']]
    assert audit['absent_on_regular_session_grid'] == ['2026-08-03T22:05:00+00:00']
    assert len(audit['gaps']) == 1


def test_end_is_exclusive_and_bar_must_fit_before_it():
    result, _ = normalize_bars(raw(['2026-08-03T16:55:00-04:00', '2026-08-03T17:00:00-04:00']),
                               cutoff='2026-08-04T00:00:00Z', start='2026-08-03T16:00:00-04:00',
                               end='2026-08-03T17:00:00-04:00')
    assert len(result) == 1
    assert result.bar_end.iloc[0] == pd.Timestamp('2026-08-03T21:00:00Z')


@pytest.mark.parametrize('times,match', [
    (['2026-08-03T18:00:00'], '时区'),
    (['2026-08-03T18:00:00-04:00'] * 2, '唯一'),
    (['2026-08-03T18:05:00-04:00', '2026-08-03T18:00:00-04:00'], '递增'),
    (['2026-08-03T18:01:00-04:00'], '五分钟'),
])
def test_invalid_time_labels_rejected(times, match):
    with pytest.raises(ValueError, match=match):
        clean(raw(times))


@pytest.mark.parametrize('column,value,match', [('Close', 0, '非法'), ('Volume', -1, '非法'),
                                               ('High', 99, '高低'), ('Close', float('inf'), '无穷')])
def test_invalid_prices_rejected(column, value, match):
    data = raw(['2026-08-03T18:00:00-04:00'])
    data[column] = value
    with pytest.raises(ValueError, match=match):
        clean(data)


def test_maintenance_and_weekend_rows_quarantined_and_dst_preserved():
    frame = raw(['2026-11-06T16:55:00-05:00', '2026-11-06T17:00:00-05:00',
                 '2026-11-07T12:00:00-05:00', '2026-11-08T18:00:00-05:00'])
    result, audit = normalize_bars(frame, cutoff='2026-11-09T00:00:00Z',
                                   start='2026-11-06T16:55:00-05:00', end='2026-11-08T18:05:00-05:00')
    assert result.bar_end.tolist() == list(pd.to_datetime(['2026-11-06T22:00:00Z', '2026-11-08T23:05:00Z']))
    assert len(audit['excluded']) == 2
    assert all(r['reasons'] == ['outside_regular_gc_hours'] for r in audit['excluded'])


def test_plot_breaks_and_intraday_drawdown_do_not_fill_gaps():
    index = pd.to_datetime(['2026-08-03T22:05:00Z', '2026-08-03T22:10:00Z',
                            '2026-08-03T22:20:00Z', '2026-08-03T22:25:00Z'])
    prices = pd.Series([100, 80, 120, 108], index=index)
    x, y = broken_line(prices)
    assert x[0] == '2026-08-03T18:05:00'
    assert y == [100, 80, None, 120, 108]
    stats = interval_stats(prices, index[0].isoformat(), index[-1].isoformat())
    assert stats['change_pct'] == pytest.approx(8)
    assert stats['max_drawdown_pct'] == pytest.approx(-20)
    assert stats['drawdown_trough'] == index[1].isoformat()
    assert interval_stats(prices, index[1].isoformat(), index[-1].isoformat())['max_drawdown_pct'] == pytest.approx(-10)


def test_loading_detects_modified_snapshot(tmp_path):
    snapshot_id = '20260911T020000Z'
    local = tmp_path / '.cache/gold-outlook/intraday/snapshots' / snapshot_id
    public = tmp_path / 'data/raw/gold-outlook'
    local.mkdir(parents=True)
    (public / 'phase1').mkdir(parents=True)
    (public / 'reviews').mkdir()
    data = local / 'gcz26.csv'
    data.write_text('bar_end,close\n2026-09-08T21:00:00Z,100\n')
    manifest = {'primary': 'gcz26', 'sample_end': '2026-09-08T17:00:00-04:00',
                'files': {'gcz26.csv': hashlib.sha256(data.read_bytes()).hexdigest()}}
    (local / 'manifest.json').write_text(json.dumps(manifest))
    (public / 'reviews' / f'intraday-{snapshot_id}.json').write_text(json.dumps(manifest))
    (public / 'phase1/intraday-input.json').write_text(json.dumps({'snapshot': snapshot_id, 'primary': 'gcz26'}))
    prices, _ = load_intraday(tmp_path)
    assert prices.iloc[0] == 100
    data.write_text(data.read_text().replace(',100', ',200'))
    with pytest.raises(ValueError, match='哈希'):
        load_intraday(tmp_path)
