import pandas as pd
import pytest

from inv.gold_analysis import drawdown, interval_stats


def series(values):
    return pd.Series(values, index=pd.to_datetime(['2026-07-31','2026-08-03','2026-08-04','2026-08-05'][:len(values)]))


def test_drawdown_is_peak_before_trough_not_full_range():
    prices = series([100, 80, 120, 108])
    assert drawdown(prices).tolist() == pytest.approx([0, -20, 0, -10])
    stats = interval_stats(prices, '2026-07-31', '2026-08-05')
    assert stats['change_pct'] == pytest.approx(8)
    assert stats['max_drawdown_pct'] == pytest.approx(-20)
    assert stats['drawdown_peak'] == '2026-07-31'
    assert stats['drawdown_trough'] == '2026-08-03'
    assert stats['intervals'] == 3
    assert stats['calendar_days'] == 5


def test_stage_restarts_peak_and_requires_observed_baseline():
    prices = series([100, 80, 120, 108])
    stats = interval_stats(prices, '2026-08-03', '2026-08-05')
    assert stats['max_drawdown_pct'] == pytest.approx(-10)
    assert stats['change_pct'] == pytest.approx(35)
    with pytest.raises(ValueError, match='实际观测'):
        interval_stats(prices, '2026-08-01', '2026-08-05')


@pytest.mark.parametrize('values', [[100, None, 120], [100, 0, 120], [100, float('inf'), 120]])
def test_no_silent_fill_or_invalid_values(values):
    with pytest.raises(ValueError, match='缺失'):
        drawdown(series(values))


def test_duplicate_and_unsorted_rejected():
    prices = series([100, 110])
    prices.index = pd.to_datetime(['2026-08-03','2026-08-03'])
    with pytest.raises(ValueError, match='唯一'):
        drawdown(prices)
    with pytest.raises(ValueError, match='递增'):
        drawdown(series([100, 110]).iloc[::-1])
