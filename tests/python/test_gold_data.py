from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests

from inv import gold_data as gold

CUTOFF = gold.timestamp("2026-09-09T11:59:46Z")


def observations() -> pd.DataFrame:
    return pd.DataFrame({
        "observation_date": ["2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09"],
        "value": [100.0, np.nan, 105.0, 106.0], "available_at": "", "known_by_at": "", "vintage_date": "",
        "session_close_at": [f"2026-09-{day:02}T17:00:00-04:00" for day in (4, 7, 8, 9)],
    })


def test_cutoff_requires_timezone_and_uses_completed_chicago_day() -> None:
    with pytest.raises(ValueError, match="时区"):
        gold.timestamp("2026-09-09T12:00:00")
    vintage, known_by = gold.completed_vintage(CUTOFF)
    assert vintage == "2026-09-08"
    assert known_by == "2026-09-09T05:00:00+00:00"
    assert gold.completed_vintage(gold.timestamp("2026-01-06T12:00:00Z"))[1] == "2026-01-06T06:00:00+00:00"


def test_price_excludes_unfinished_session_and_preserves_missing_holiday() -> None:
    result = gold.validate_observations(observations(), CUTOFF, price=True)
    assert result["observation_date"].tolist() == ["2026-09-04", "2026-09-07", "2026-09-08"]
    assert pd.isna(result.loc[1, "value"])


@pytest.mark.parametrize("field", ["available_at", "known_by_at"])
def test_observation_cannot_arrive_before_release_or_vintage_bound(field: str) -> None:
    frame = observations().iloc[:3].copy()
    frame.loc[2, field] = "2026-09-11T15:30:00-04:00"
    result = gold.validate_observations(frame, CUTOFF)
    assert "2026-09-08" not in result["observation_date"].tolist()


def test_duplicate_price_dates_are_rejected_instead_of_silently_merged() -> None:
    frame = observations()
    frame.loc[1, "observation_date"] = frame.loc[0, "observation_date"]
    with pytest.raises(ValueError, match="重复"):
        gold.validate_observations(frame, CUTOFF)


@pytest.mark.parametrize("value", [0, -1, float("inf")])
def test_invalid_gold_prices_are_rejected(value: float) -> None:
    frame = observations()
    frame.loc[0, "value"] = value
    with pytest.raises(ValueError):
        gold.validate_observations(frame, CUTOFF, price=True)


def test_price_close_time_is_required() -> None:
    with pytest.raises(ValueError, match="session_close_at"):
        gold.validate_observations(observations().drop(columns="session_close_at"), CUTOFF, price=True)


def test_authentication_errors_do_not_echo_secret_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise requests.RequestException("https://example.test/?api_key=secret-value")
    monkeypatch.setattr(gold.requests, "get", fail)
    monkeypatch.setattr(gold.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError) as caught:
        gold.download("https://example.test", params={"api_key": "secret-value"})
    assert "secret-value" not in str(caught.value)
    assert "api_key" not in str(caught.value)


def test_cached_fred_retains_vintage_and_missing_observations(tmp_path: Path) -> None:
    payload = {"retrieved_at": "2026-09-09T12:30:00Z", "payload": {"observations": [
        {"date": "2026-09-04", "value": "4.37"}, {"date": "2026-09-07", "value": "."},
    ]}}
    (tmp_path / "DGS2-2026-09-08.json").write_text(json.dumps(payload))
    frame, _ = gold.fred_snapshot("DGS2", CUTOFF, tmp_path, refresh=False)
    assert frame["vintage_date"].unique().tolist() == ["2026-09-08"]
    assert frame["available_at"].eq("").all()
    assert pd.isna(frame.loc[1, "value"])


def stub_fetches(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = observations().iloc[:3].drop(columns="session_close_at")
    monkeypatch.setattr(gold, "fred_snapshot", lambda *a, **k: (frame, {"retrieved_at": "2026-09-09T12:30:00Z"}))
    monkeypatch.setattr(gold, "cftc_snapshot", lambda *a, **k: (frame, {"retrieved_at": "2026-09-09T12:30:00Z"}))


def test_snapshot_is_immutable_and_detects_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_fetches(monkeypatch)
    path = gold.build_snapshot(CUTOFF, root=tmp_path)
    manifest = gold.verify_snapshot(path)
    assert manifest["primary_price_status"] == "pending_futures_review"
    assert manifest["primary_price_series"] == "gold"
    assert manifest["phase_1_authorized"] is False
    with pytest.raises(ValueError, match="不得覆盖"):
        gold.build_snapshot(CUTOFF, root=tmp_path)
    (path / "ust2y.csv").write_text("corrupt")
    with pytest.raises(ValueError, match="哈希"):
        gold.verify_snapshot(path)


def test_restricted_source_cannot_be_imported_into_public_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_fetches(monkeypatch)
    imports = tmp_path / "imports"
    imports.mkdir()
    observations().to_csv(imports / "xauusd.csv", index=False)
    with pytest.raises(ValueError, match="公开保存权限"):
        gold.build_snapshot(CUTOFF, root=tmp_path / "public", imports=imports)
    assert not (tmp_path / "public/snapshots").exists()


def test_cftc_observation_waits_for_friday_release(tmp_path: Path) -> None:
    columns = ["CFTC_Contract_Market_Code", "Market_and_Exchange_Names", "Report_Date_as_YYYY-MM-DD",
               "M_Money_Positions_Long_All", "M_Money_Positions_Short_All",
               "M_Money_Positions_Spread_All", "Open_Interest_All"]
    for year in range(2023, 2027):
        dates = [f"{year}-08-01"] if year < 2026 else ["2026-09-01", "2026-09-08"]
        frame = pd.DataFrame([["088691", "GOLD - COMMODITY EXCHANGE INC.", day, 100, 40, 10, 300]
                              for day in dates], columns=columns)
        with zipfile.ZipFile(tmp_path / f"cftc-{year}.zip", "w") as archive:
            archive.writestr("f_year.txt", frame.to_csv(index=False))
        (tmp_path / f"cftc-{year}.json").write_text(json.dumps({"retrieved_at": "2026-09-09T12:30:00Z"}))
    releases = {"2026-09-01": "2026-09-04T15:30:00-04:00", "2026-09-08": "2026-09-11T15:30:00-04:00"}
    frame, _ = gold.cftc_snapshot(CUTOFF, tmp_path, releases, refresh=False)
    assert frame["observation_date"].iloc[-1] == "2026-09-01"
    assert frame["value"].iloc[-1] == 60
    assert frame["available_at"].iloc[0] == ""
