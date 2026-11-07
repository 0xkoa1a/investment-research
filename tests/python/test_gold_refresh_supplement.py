from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from inv import gold_refresh_supplement as supplement

NY = ZoneInfo('America/New_York')


def fedwatch_frame() -> pd.DataFrame:
    return pd.DataFrame({
        'Date': ['09/15/2026', '09/16/2026', '09/17/2026', '09/23/2026', '09/25/2026'],
        '(300-325)': [.1, .1, .2, .1, .1],
        '(325-350)': [.2, .2, .3, .2, .2],
        '(350-375)': [.5, .5, .4, .5, .5],
        '(375-400)': [.2, .2, .1, .2, .2],
    })


def policies() -> pd.DataFrame:
    return pd.DataFrame({'date': ['2026-09-01', '2026-09-16'],
                         'lower_bp': [350, 325], 'upper_bp': [375, 350]})


def test_fedwatch_uses_policy_effective_for_observation_date_and_drops_after_meeting():
    out = supplement.normalize_fedwatch(
        fedwatch_frame(), '2026-09-23', datetime(2026, 9, 26, 0, tzinfo=NY), policies()
    )
    assert out.index.strftime('%Y-%m-%d').tolist() == ['2026-09-15', '2026-09-16', '2026-09-17']
    assert out.loc['2026-09-15', 'lower_pct'] == pytest.approx(30)
    assert out.loc['2026-09-15', 'unchanged_pct'] == pytest.approx(50)
    assert out.loc['2026-09-15', 'higher_pct'] == pytest.approx(20)
    assert out.loc['2026-09-17', 'lower_pct'] == pytest.approx(20)
    assert out.loc['2026-09-17', 'unchanged_pct'] == pytest.approx(30)
    assert out.loc['2026-09-17', 'higher_pct'] == pytest.approx(50)
    assert out.loc['2026-09-23':].empty


def test_policy_change_day_is_ambiguous_but_raw_target_distribution_is_preserved():
    out = supplement.normalize_fedwatch(
        fedwatch_frame(), '2026-09-23', datetime(2026, 9, 26, 0, tzinfo=NY), policies()
    )
    row = out.loc['2026-09-16']
    assert row.ambiguous_policy_day
    assert pd.isna(row.lower_pct) and pd.isna(row.unchanged_pct) and pd.isna(row.higher_pct)
    assert row['(325-350)'] == pytest.approx(.2)


def test_announcement_day_is_ambiguous_before_fred_effective_date():
    policy = pd.DataFrame({'date': ['2026-09-01', '2026-09-17'],
                           'lower_bp': [350, 325], 'upper_bp': [375, 350]})
    out = supplement.normalize_fedwatch(
        fedwatch_frame(), '2026-09-23', datetime(2026, 9, 26, 0, tzinfo=NY), policy,
        announcement_dates=('2026-09-16',),
    )
    announcement = out.loc['2026-09-16']
    assert announcement.ambiguous_policy_day
    assert pd.isna(announcement.lower_pct)
    assert pd.isna(announcement.unchanged_pct)
    assert pd.isna(announcement.higher_pct)
    assert announcement['(350-375)'] == pytest.approx(.5)
    # The announcement day is not misclassified using the old range; after implementation,
    # the new range is reflected on the FRED effective date.
    effective = out.loc['2026-09-17']
    assert effective.ambiguous_policy_day


def test_fedwatch_excludes_incomplete_cutoff_ny_date():
    out = supplement.normalize_fedwatch(
        fedwatch_frame(), '2026-09-30', datetime(2026, 9, 25, 16, tzinfo=NY), policies()
    )
    assert '2026-09-25' not in out.index.strftime('%Y-%m-%d')


class Response:
    status_code = 200
    url = supplement.GLD_ARCHIVE_URL
    headers = {'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}

    def __init__(self, content: bytes):
        self.content = content


def workbook() -> bytes:
    buffer = BytesIO()
    raw = pd.DataFrame({'Date': ['04-Sep-2026', '07-Sep-2026', '08-Sep-2026', '09-Sep-2026'],
                        'Tonnes of Gold': [1052.06, 'US Holiday', 1050.63, 1051.0]})
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        raw.to_excel(writer, sheet_name='US GLD Historical Archive', index=False)
    return buffer.getvalue()


def test_gld_download_preserves_holiday_nan_and_excludes_cutoff_date(tmp_path, monkeypatch):
    content = workbook()
    monkeypatch.setattr(supplement.requests, 'get', lambda *args, **kwargs: Response(content))
    out, metadata = supplement.fetch_gld(
        datetime(2026, 9, 4, tzinfo=NY), datetime(2026, 9, 9, 12, tzinfo=NY), tmp_path
    )
    assert out.date.tolist() == ['2026-09-04', '2026-09-07', '2026-09-08']
    assert out.holiday.tolist() == [False, True, False]
    assert np.isnan(out.loc[1, 'tonnes'])
    assert metadata['first_publication_at'] is None
    assert metadata['observation_frequency'] == 'NYSE trading-day daily archive'
    assert metadata['sha256']
    assert (tmp_path / metadata['raw_file']).read_bytes() == content


def test_gld_rejects_html_error_response_without_writing_xlsx(tmp_path, monkeypatch):
    monkeypatch.setattr(supplement.requests, 'get', lambda *args, **kwargs: Response(b'<html>error</html>'))
    with pytest.raises(ValueError, match='XLSX'):
        supplement.fetch_gld(
            datetime(2026, 9, 4, tzinfo=NY), datetime(2026, 9, 9, tzinfo=NY), tmp_path
        )
    assert not list(tmp_path.glob('*.xlsx'))
