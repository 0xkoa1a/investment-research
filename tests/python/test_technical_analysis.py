"""Verify the tutorial's mathematical examples and causal data boundaries."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("technical_analysis", ROOT / "scripts/research/technical-analysis.py")
assert spec is not None and spec.loader is not None
ta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ta)


def test_falling_close_can_accompany_rising_sma():
    prices = pd.Series([100, 102, 104, 106, 108, 106], dtype=float)
    averages = prices.rolling(5).mean()
    assert averages.iloc[-2:].tolist() == pytest.approx([104, 105.2])
    assert averages.iloc[-1] - averages.iloc[-2] == pytest.approx((106 - 100) / 5)
    position = ta.teaching_data()["position"]
    assert position.close.iloc[-1] < position.sma60.iloc[-1]
    assert position.sma60.iloc[-1] > position.sma60.iloc[-2]


def test_gap_enters_true_range_and_wilder_initialization():
    bars = pd.DataFrame({"close": [100, 107], "high": [100, 108], "low": [100, 105]})
    assert ta.true_range(bars).tolist() == [0, 8]
    values = pd.Series([np.nan, *range(1, 16)], dtype=float)
    smoothed = ta.wilder(values)
    assert smoothed.iloc[:14].isna().all()
    assert smoothed.iloc[14] == 7.5
    assert smoothed.iloc[15] == pytest.approx((7.5 * 13 + 15) / 14)


def test_macd_constant_speed_limit():
    result = ta.indicators(pd.Series(np.arange(1000, dtype=float) + 100))
    assert result.dif.iloc[-1] == pytest.approx(7, abs=1e-10)
    assert result.dea.iloc[-1] == pytest.approx(7, abs=1e-10)
    assert result.histogram.iloc[-1] == pytest.approx(0, abs=1e-10)


def test_histogram_can_shrink_while_dif_rises():
    signal = ta.ema(pd.Series([2.5, 3.1]), 9)
    assert signal.iloc[-1] == pytest.approx(2.62)
    assert 0 < 3.1 - signal.iloc[-1] < 3 - 2.5


def test_rsi_single_direction_and_initial_flat_boundary():
    up = ta.rsi(pd.Series(np.arange(20, dtype=float)))
    down = ta.rsi(pd.Series(-np.arange(20, dtype=float)))
    assert up.iloc[:14].isna().all()
    assert (up.iloc[14:] == 100).all()
    assert (down.iloc[14:] == 0).all()
    assert ta.rsi(pd.Series([100.0] * 30)).isna().all()


def test_rsi_includes_zero_periods_and_keeps_ratio_during_flat_prices():
    # Seven +2 changes, seven -1 changes: initial U=1, D=0.5, RSI=66 2/3.
    changes = [2, -1] * 7
    prices = pd.Series([100, *(100 + np.cumsum(changes))], dtype=float)
    prices = pd.concat([prices, pd.Series([prices.iloc[-1]] * 20)], ignore_index=True)
    result = ta.rsi(prices)
    np.testing.assert_allclose(result.iloc[14:], 200 / 3)
    pd.testing.assert_series_equal(result, ta.rsi(prices * 10))


def test_indicators_do_not_use_future_values():
    data = ta.teaching_data()
    close = data["momentum"].close
    for end in (50, 100, 120, 149):
        pd.testing.assert_frame_equal(ta.indicators(close.loc[:end]), ta.indicators(close).loc[:end])
    bars = data["position"]
    pd.testing.assert_series_equal(ta.wilder(ta.true_range(bars.loc[:100])), bars.atr14.loc[:100], check_names=False)


def test_teaching_cases_preserve_the_intended_comparisons():
    data = ta.teaching_data()
    b, m, p = data["breakout"], data["momentum"], data["profile"]
    assert b.loc[21, "volume"] == 2 * b.loc[:20, "volume"].mean()
    assert b.high.max() == 118
    assert b.loc[30, "low"] == 109.8
    assert b.loc[30, "close"] == 112
    assert m.loc[149, "close"] > m.loc[100, "close"]
    assert m.loc[111:148, "close"].between(112, 125.5, inclusive="neither").all()
    assert m.loc[150:155, "close"].max() < m.loc[149, "close"]
    position = data["position"].close
    for low in (80, 110):
        assert position.loc[low] < min(position.loc[low - 1], position.loc[low + 1])
    assert m.loc[149, "dif"] < m.loc[100, "dif"]
    assert m.loc[149, "rsi14"] < m.loc[100, "rsi14"]
    assert m.loc[155, "dif"] > 0 > m.loc[155, "histogram"]
    assert p.volume.sum() == 10000
    area = p.loc[p.value_area]
    assert (area.lower.min(), area.upper.max(), area.volume.sum()) == (110, 124, 7000)
    assert p.loc[p.volume.idxmax(), "lower"] == 114
    for bars in (b, data["position"]):
        assert (bars.high >= bars[["open", "close"]].max(axis=1)).all()
        assert (bars.low <= bars[["open", "close"]].min(axis=1)).all()


def test_bollinger_price_dispersion_and_retracement_denominators():
    bands = ta.teaching_data()["bands"]
    assert bands.loc[50, "std"] < bands.loc[30, "std"]
    assert bands.loc[100, "middle"] > bands.loc[80, "middle"]
    assert 140 - 0.618 * (140 - 100) == pytest.approx(115.28)
    assert (140 - 116) / (140 - 100) == pytest.approx(0.6)
    assert (140 - 116) / (140 - 110) == pytest.approx(0.8)
    assert (140 - 116) / 140 == pytest.approx(0.1714285714)


def test_ohlc_aggregation_preserves_extremes_and_period_boundaries():
    bars = pd.DataFrame({"open": [10, 12, 11, 15], "high": [14, 13, 16, 18],
                         "low": [9, 10, 8, 14], "close": [12, 11, 15, 17]})
    result = ta.aggregate_bars(bars, 2)
    expected = pd.DataFrame({"open": [10, 11], "high": [14, 18],
                             "low": [9, 8], "close": [11, 17]}, index=[1, 2])
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(ta.aggregate_bars(result, 2), ta.aggregate_bars(bars, 4))
    with pytest.raises(ValueError, match="完整教学周期"):
        ta.aggregate_bars(bars.iloc[:3], 2)


def test_timeframes_share_history_and_observation_cutoff():
    data = ta.teaching_data()
    hourly, daily, weekly = [data[f"timeframe_{scale}"] for scale in ("hourly", "daily", "weekly")]
    assert [len(hourly), len(daily), len(weekly)] == [840, 210, 42]
    for frame in (hourly, daily, weekly):
        assert frame.close.iloc[-1] == 108
        assert frame.high.max() == 160
        assert frame.low.min() == 80
        assert frame.low.iloc[-1] == 106.8
        assert (frame.high >= frame[["open", "close"]].max(axis=1)).all()
        assert (frame.low <= frame[["open", "close"]].min(axis=1)).all()
    pd.testing.assert_frame_equal(ta.aggregate_bars(hourly, 20), weekly)
    pd.testing.assert_frame_equal(ta.aggregate_bars(hourly.loc[:800], 4), daily.loc[:200])
    assert daily.loc[[170, 176, 180, 186, 190, 196, 200, 206, 210], "close"].tolist() == [
        80, 92, 86, 100, 94, 110, 103, 112, 108]
    assert weekly.loc[42, "high"] == 112
    assert hourly.loc[821:, "low"].min() > daily.loc[200, "close"]


def test_breakout_branches_only_diverge_after_common_observation():
    paths = ta.teaching_data()["breakout_paths"]
    assert paths.loc[21].tolist() == [112, 112, 112]
    assert paths.loc[:20, ["path_a", "path_b"]].isna().all().all()
    assert paths.loc[22:, "history"].isna().all()
    assert paths.loc[24, "path_a"] == 110.6
    assert paths.loc[27, ["path_a", "path_b"]].tolist() == [116, 104]


def test_fibonacci_levels_begin_when_the_high_is_confirmable():
    data = ta.teaching_data()
    close = data["position"].close
    high = close.idxmax()
    assert high == 130
    assert (close.loc[high - 2:high - 1] < close.loc[high]).all()
    assert (close.loc[high + 1:high + 2] < close.loc[high]).all()
    chart = ta.build_charts(data)["fibonacci-anchors"]
    for trace in chart.data[1:]:
        assert min(trace.x) == high + 2
        assert min(trace.x) > high


def test_pattern_examples_separate_formation_from_subsequent_break():
    patterns = ta.teaching_data()["patterns"]
    top = patterns.double_top.dropna()
    assert top.iloc[:-1].iloc[2:].min() >= 112 > top.iloc[-1]
    head = patterns.head_shoulders.dropna()
    assert head.loc[4] > max(head.loc[2], head.loc[6])
    assert head.loc[3] == head.loc[5] == 108 > head.iloc[-1]
    triangle = patterns.triangle.dropna()
    assert (triangle.loc[[2, 4, 6]] == 110).all()
    assert triangle.loc[1] < triangle.loc[3] < triangle.loc[5] < 110 < triangle.iloc[-1]
    wedge = patterns.wedge.dropna()
    assert wedge.loc[1] < wedge.loc[3] < wedge.loc[5]
    assert wedge.loc[2] < wedge.loc[4] < wedge.loc[6]
    assert wedge.loc[2] - wedge.loc[1] > wedge.loc[4] - wedge.loc[3] > wedge.loc[6] - wedge.loc[5]
    assert wedge.iloc[-1] < wedge.loc[5]
