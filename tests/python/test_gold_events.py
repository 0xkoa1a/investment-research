import pandas as pd
import pytest

from inv.gold_events import announcement_reaction, driver_change, event_session, event_window


def calendar():
    return pd.bdate_range('2026-08-27', '2026-09-09').difference(pd.to_datetime(['2026-09-07']))


def prices():
    return pd.Series([100, 110, 99, 98, 97, 96, 95, 94, 93],
                     index=(calendar() + pd.Timedelta(hours=17)).tz_localize('America/New_York'))


def test_weekend_and_after_close_use_next_verified_session():
    assert event_session('2026-08-28T20:59:00Z', calendar()) == '2026-08-28'
    assert event_session('2026-08-28T21:00:00Z', calendar()) == '2026-08-31'
    assert event_session('2026-08-30T20:00:00Z', calendar()) == '2026-08-31'
    assert event_session('2026-09-04T17:01:00-04:00', calendar()) == '2026-09-08'
    with pytest.raises(ValueError, match='时区'):
        event_session('2026-08-28T10:00:00', calendar())


def test_fixed_horizons_respect_holiday_and_cumulative_base():
    out = event_window(prices(), '2026-08-31', calendar(), '2026-09-08T17:00:00-04:00')
    assert out['baseline']['close'] == 110
    assert [w['date'] for w in out['windows']] == ['2026-08-31', '2026-09-01', '2026-09-03', '2026-09-08']
    assert out['windows'][0]['change_pct'] == pytest.approx(-10)
    assert out['windows'][-1]['close'] == 94


def test_missing_price_never_shifts_event_day_or_horizon():
    raw = prices().drop(pd.Timestamp('2026-09-01T17:00:00-04:00'))
    out = event_window(raw, '2026-08-31', calendar(), '2026-09-08T17:00:00-04:00')
    assert out['windows'][1]['date'] == '2026-09-01'
    assert out['windows'][1]['status'] == 'missing_price'
    assert out['windows'][1]['change_pct'] is None
    assert out['windows'][2]['close'] == 96


def test_unfinished_endpoint_is_null_even_if_input_contains_future_price():
    out = event_window(prices(), '2026-08-31', calendar(), '2026-09-08T16:59:00-04:00')
    assert out['windows'][-1]['status'] == 'not_completed'
    assert out['windows'][-1]['close'] is None
    raw = prices().drop(pd.Timestamp('2026-08-28T17:00:00-04:00'))
    out = event_window(raw, '2026-08-31', calendar(), '2026-09-08T17:00:00-04:00')
    assert all(w['change_pct'] is None for w in out['windows'])


def test_release_boundary_is_not_pre_event_and_missing_prebar_is_not_filled():
    index = pd.date_range('2026-08-28T09:50:00-04:00', periods=5, freq='5min')
    raw = pd.Series([90, 100, 120, 110, 100], index=index)
    out = announcement_reaction(raw, '2026-08-28T14:00:00Z', '2026-08-28T17:00:00-04:00')
    assert out['before']['close'] == 100
    assert out['after'][0]['change_from_before_pct'] == pytest.approx(10)
    assert out['after'][1]['status'] == 'missing_price'
    out = announcement_reaction(raw.drop(index[1]), '2026-08-28T14:00:00Z', '2026-08-28T17:00:00-04:00')
    assert out['before']['close'] is None
    assert out['after'][0]['change_from_before_pct'] is None


def test_driver_units_and_source_lag_no_stale_endpoint():
    series = pd.Series([2.34, 2.42], index=pd.to_datetime(['2026-08-27', '2026-08-28']))
    assert driver_change(series, '2026-08-27', '2026-08-28', 'bp')['change'] == pytest.approx(8)
    assert driver_change(series, '2026-08-27', '2026-08-31', 'bp')['end'] is None
    prob = series * 10
    assert driver_change(prob, '2026-08-27', '2026-08-28', 'percentage_points')['change'] == pytest.approx(.8)
