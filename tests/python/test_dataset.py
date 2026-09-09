from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from inv.dataset import add_derived, align_available


def test_available_panel_uses_real_sessions_and_conservative_release_activation() -> None:
    sessions = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-04-20"])
    prices = pd.DataFrame(
        {
            "spx": [100.0, 101.0, 102.0, 103.0, 110.0],
            "gold": [200.0, np.nan, 210.0, 211.0, 220.0],
        },
        index=sessions,
    )
    releases = pd.DataFrame({"cpi": [300.0]}, index=pd.to_datetime(["2026-01-06"]))
    panel = align_available(releases, prices)
    assert pd.isna(panel.loc["2026-01-06", "cpi"])
    assert panel.loc["2026-01-07", "cpi"] == 300.0
    assert pd.isna(panel.loc["2026-04-20", "cpi"])
    assert pd.isna(panel.loc["2026-01-05", "gold"])

    derived = add_derived(panel)
    expected = np.log(210.0 / 200.0)
    assert derived.loc["2026-01-06", "ret_gold"] == pytest.approx(expected)


def test_available_panel_requires_observed_market_calendar() -> None:
    releases = pd.DataFrame({"cpi": [300.0]}, index=pd.to_datetime(["2026-01-06"]))
    prices = pd.DataFrame({"gold": [200.0]}, index=pd.to_datetime(["2026-01-06"]))
    try:
        align_available(releases, prices)
    except ValueError as error:
        assert "不能用工作日伪造交易日" in str(error)
    else:
        raise AssertionError("缺少 SPX 时必须失败")
