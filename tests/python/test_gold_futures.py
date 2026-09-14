import pandas as pd
import pytest

from inv.gold_data import timestamp
from inv.gold_futures import completed_prices


def sample():
    return pd.DataFrame({'date': ['2026-09-08', '2026-09-09'], 'open': [100, 101],
                         'high': [103, 104], 'low': [99, 100], 'close': [102, 103], 'volume': [0, 4]})


def test_cutoff_preserves_zero_volume_and_excludes_current_day():
    result = completed_prices(sample(), timestamp('2026-09-09T12:00:00Z'))
    assert result.date.tolist() == ['2026-09-08']
    assert result.volume.tolist() == [0]
    assert result.known_by_boundary.iloc[0] == '2026-09-09T00:00:00-04:00'


def test_utc_date_does_not_complete_new_york_session():
    result = completed_prices(sample(), timestamp('2026-09-09T01:00:00Z'))
    assert result.empty


def test_missing_close_remains_missing():
    frame = sample()
    frame.loc[0, 'close'] = float('nan')
    assert completed_prices(frame, timestamp('2026-09-09T12:00:00Z')).close.isna().all()


def test_duplicates_and_invalid_ohlc_rejected():
    frame = sample()
    frame.loc[1, 'date'] = frame.loc[0, 'date']
    with pytest.raises(ValueError, match='重复'):
        completed_prices(frame, timestamp('2026-09-09T12:00:00Z'))
    frame = sample()
    frame.loc[0, 'high'] = 100
    with pytest.raises(ValueError, match='高低'):
        completed_prices(frame, timestamp('2026-09-09T12:00:00Z'))
