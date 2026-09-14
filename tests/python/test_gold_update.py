import numpy as np
import pandas as pd
import pytest

from inv.gold_update import checked_fedwatch, compare_versions, daily_closes, future_calendar


def series(values, dates):
    return pd.Series(values, index=pd.to_datetime(dates))


def test_revision_is_separate_from_new_observation_change():
    old = series([100, 110], ['2026-09-04', '2026-09-08'])
    new = series([100, 112, 115], ['2026-09-04', '2026-09-08', '2026-09-10'])
    result = compare_versions(old, new)
    assert result['revision_at_old_date'] == 2
    assert result['change_since_old_observation'] == 3
    assert result['change_pct_since_old_observation'] == pytest.approx((115 / 112 - 1) * 100)
    assert result['revised_overlap_dates'] == ['2026-09-08T00:00:00']


def test_lag_does_not_become_new_zero_move_and_missing_base_is_not_filled():
    old = series([100, 110], ['2026-09-04', '2026-09-08'])
    lagged = series([100, 110, np.nan], ['2026-09-04', '2026-09-08', '2026-09-10'])
    assert compare_versions(old, lagged)['status'] == 'no_new_observation'
    missing_base = series([100, np.nan, 120], ['2026-09-04', '2026-09-08', '2026-09-10'])
    result = compare_versions(old, missing_base)
    assert result['change_since_old_observation'] is None
    assert result['missing_old_dates'] == ['2026-09-08T00:00:00']
    with pytest.raises(ValueError, match='覆盖'):
        compare_versions(old, old.iloc[:1])
    with pytest.raises(ValueError, match='唯一'):
        compare_versions(old, pd.concat([old, old.iloc[-1:]]))


def test_daily_closes_do_not_use_nearby_bar_when_endpoint_missing():
    raw = series([100, 110, 120], ['2026-09-08T16:55:00-04:00', '2026-09-08T17:00:00-04:00',
                                  '2026-09-09T16:55:00-04:00'])
    result = daily_closes(raw)
    assert len(result) == 1
    assert result.index[0] == pd.Timestamp('2026-09-08')
    assert result.iloc[0] == 110


def test_future_calendar_handles_cutoff_and_daylight_saving():
    events = [{'id': 'already', 'scheduled_at': '2026-09-11T10:28:05Z'},
              {'id': 'sep', 'scheduled_at': '2026-09-11T08:30:00-04:00'},
              {'id': 'nov', 'scheduled_at': '2026-11-06T08:30:00-05:00'}]
    result = future_calendar(events, '2026-09-11T10:28:05Z')
    assert [e['id'] for e in result] == ['sep', 'nov']
    assert result[0]['beijing'] == '2026-09-11T20:30:00+08:00'
    assert result[1]['beijing'] == '2026-11-06T21:30:00+08:00'
    assert result[0]['within_four_weeks'] is True
    assert result[1]['within_four_weeks'] is False
    events[1]['actual'] = {'cpi': 3}
    with pytest.raises(ValueError, match='未来事件'):
        future_calendar(events, '2026-09-11T10:28:05Z')


def test_http_success_html_is_not_fedwatch_csv(tmp_path):
    path = tmp_path / 'probability.csv'
    path.write_text('<!doctype html><title>QuikStrike Error</title>')
    with pytest.raises(ValueError, match='HTML'):
        checked_fedwatch(path)
