import numpy as np
import pandas as pd
import pytest

from inv.gold_data import timestamp
from inv.gold_drivers import common_change, date_window, fedwatch, gld_holdings, released_cot


def probabilities():
    return pd.DataFrame({'Date': ['08/25/2026'], '(325-350)': [.1], '(350-375)': [.3],
                         '(375-400)': [.4], '(400-425)': [.2]})


def test_policy_target_distribution_and_units():
    out = fedwatch(probabilities()).iloc[0]
    assert out.lower_pct == pytest.approx(10)
    assert out.unchanged_pct == pytest.approx(30)
    # Both higher buckets count; this is not only the next +25bp bucket.
    assert out.higher_pct == pytest.approx(60)
    assert out['(400-425)'] == .2
    raw = probabilities()
    raw.iloc[:, 1:] *= 100
    with pytest.raises(ValueError, match='0—1'):
        fedwatch(raw)


def test_probability_mass_missing_and_date_validation():
    raw = probabilities()
    raw['(400-425)'] = .19
    with pytest.raises(ValueError, match='之和'):
        fedwatch(raw)
    raw = probabilities()
    raw['(350-375)'] = np.nan
    with pytest.raises(ValueError, match='内部缺失'):
        fedwatch(raw)
    raw = probabilities()
    raw.insert(1, '(300-325)', np.nan)
    raw['(425-450)'] = np.nan
    assert pd.isna(fedwatch(raw).iloc[0]['(425-450)'])
    assert fedwatch(raw).iloc[0].higher_pct == pytest.approx(60)
    with pytest.raises(ValueError, match='重复'):
        fedwatch(pd.concat([probabilities(), probabilities()]))


def test_daily_cutoff_excludes_unfinished_date_and_respects_sample_end():
    frame = pd.DataFrame({'value': [100, np.nan, 101, 102]},
                         index=pd.to_datetime(['2026-07-31', '2026-08-03', '2026-08-04', '2026-08-05']))
    out = date_window(frame, '2026-08-05', timestamp('2026-08-04T23:59:00-04:00'))
    assert out.index[-1] == pd.Timestamp('2026-08-03')
    assert pd.isna(out.iloc[-1].value)
    out = date_window(frame, '2026-08-03', timestamp('2026-08-06T00:00:00-04:00'))
    assert len(out) == 2


def test_gld_holiday_does_not_become_a_flow_or_a_zero():
    raw = pd.DataFrame({'Date': ['04-Sep-2026', '07-Sep-2026', '08-Sep-2026'],
                        'Tonnes of Gold': [1052.06, 'US Holiday', 1050.63]})
    out = gld_holdings(raw)
    assert out.holiday.tolist() == [False, True, False]
    assert pd.isna(out.iloc[1].tonnes)
    raw.loc[1, 'Tonnes of Gold'] = 'source error'
    with pytest.raises(ValueError):
        gld_holdings(raw)


def cot_frame():
    return pd.DataFrame({
        'observation_date': ['2026-08-25', '2026-09-01', '2026-09-08'],
        'available_at': ['2026-08-28T15:30:00-04:00', '2026-09-04T15:30:00-04:00', '2026-09-11T15:30:00-04:00'],
        'managed_money_long': [159819, 149721, 145000], 'managed_money_short': [15072, 12950, 12000],
        'managed_money_spreading': [16251, 27264, 20000], 'open_interest': [427957, 415196, 400000],
        'value': [144747, 136771, 133000]})


def test_cot_availability_and_long_liquidation_vs_short_cover():
    out = released_cot(cot_frame(), '2026-09-09T11:59:46Z')
    assert out.index[-1] == pd.Timestamp('2026-09-01')
    assert out.iloc[-1].long_change == -10098
    assert out.iloc[-1].short_contribution == 2122
    assert out.iloc[-1].net_change == -7976
    raw = cot_frame()
    raw.loc[1, 'value'] += 1
    with pytest.raises(ValueError, match='净额'):
        released_cot(raw, '2026-09-09T11:59:46Z')


def test_cot_unknown_publication_and_missing_week_not_forward_filled():
    raw = cot_frame()
    raw.loc[1, 'available_at'] = None
    out = released_cot(raw, '2026-09-12T00:00:00Z')
    assert len(out) == 2
    assert pd.isna(out.iloc[-1].net_change)


def test_common_window_shortens_endpoint_without_stale_rate():
    dates = pd.to_datetime(['2026-08-25', '2026-09-04', '2026-09-08'])
    gold = pd.Series([4715.9, 4476.6, 4400], index=dates)
    rate = pd.Series([2.32, 2.43, np.nan], index=dates)
    out = common_change({'gold': gold, 'real': rate}, '2026-08-25', '2026-09-08')
    assert out['end'] == '2026-09-04'
    assert out['values']['gold']['change_pct'] == pytest.approx(-5.0743, abs=.0001)
    assert out['values']['real']['change'] * 100 == pytest.approx(11)
    with pytest.raises(ValueError, match='起始'):
        common_change({'gold': gold, 'real': rate.iloc[1:]}, '2026-08-25', '2026-09-08')
