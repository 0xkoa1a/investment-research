from __future__ import annotations

import pandas as pd
import pytest

from inv import fetch_fred
from inv.fetch_fred import _first_releases


class FakeFred:
    api_key = "test-key"


def fake_api_json(_fred, endpoint: str, **parameters) -> dict:
    if endpoint == "series/vintagedates":
        return {"vintage_dates": [{"date": "1994-02-17"}]}
    if parameters["output_type"] == 1:
        return {
            "observations": [
                {"date": "1990-01-01", "realtime_start": "1994-02-17", "value": "127.5"}
            ]
        }
    return {
        "observations": [
            {"date": "1990-02-01", "realtime_start": "1994-03-17", "value": "128.0"}
        ]
    }


def test_first_release_combines_earliest_snapshot_and_initial_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_fred, "_fred_api_json", fake_api_json)
    latest = pd.DataFrame({"cpi": [127.5]}, index=pd.to_datetime(["1990-01-01"]))
    result = _first_releases(FakeFred(), "CPIAUCSL", "cpi", frequency="M", latest=latest)
    assert result is not None
    assert result.loc["1990-01-01", "available_date"] == pd.Timestamp("1994-02-17")
    assert result.loc["1990-01-01", "cpi"] == 127.5
    assert result.loc["1990-02-01", "available_date"] == pd.Timestamp("1994-03-17")


def no_alfred_api_json(_fred, _endpoint: str, **_parameters) -> dict:
    return {"vintage_dates": []}


def test_daily_series_without_alfred_uses_next_session_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_fred, "_fred_api_json", no_alfred_api_json)
    latest = pd.DataFrame({"rate": [1.0]}, index=pd.to_datetime(["2026-01-02"]))
    result = _first_releases(FakeFred(), "RATE", "rate", frequency="D", latest=latest)
    assert result is not None
    assert result.loc["2026-01-02", "available_date"] == pd.Timestamp("2026-01-02")


def test_monthly_series_without_alfred_is_not_invented(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_fred, "_fred_api_json", no_alfred_api_json)
    latest = pd.DataFrame({"macro": [1.0]}, index=pd.to_datetime(["2026-01-01"]))
    result = _first_releases(FakeFred(), "MACRO", "macro", frequency="M", latest=latest)
    assert result is not None
    assert result.empty


def test_rejects_saturated_initial_release_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_fred, "FRED_OBSERVATION_LIMIT", 2)

    def saturated_api_json(_fred, endpoint: str, **parameters) -> dict:
        if endpoint == "series/vintagedates":
            return {"vintage_dates": [{"date": "2026-01-02"}]}
        if parameters["output_type"] == 1:
            return {"observations": []}
        return {
            "observations": [
                {"date": "2026-01-01", "realtime_start": "2026-01-02", "value": "1"},
                {"date": "2026-01-02", "realtime_start": "2026-01-03", "value": "2"},
            ]
        }

    monkeypatch.setattr(fetch_fred, "_fred_api_json", saturated_api_json)
    latest = pd.DataFrame({"macro": [2.0]}, index=pd.to_datetime(["2026-01-02"]))
    assert _first_releases(FakeFred(), "MACRO", "macro", frequency="M", latest=latest) is None
