from __future__ import annotations

from pathlib import Path

import pandas as pd

from inv.storage import upsert_csv, write_csv


def test_upsert_preserves_history_and_overrides_same_date(tmp_path: Path) -> None:
    path = tmp_path / "series.csv"
    old = pd.DataFrame({"value": [1.0, 2.0]}, index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    new = pd.DataFrame({"value": [3.0, 4.0]}, index=pd.to_datetime(["2026-01-02", "2026-01-03"]))
    write_csv(path, old)
    total, added = upsert_csv(path, new)
    result = pd.read_csv(path, parse_dates=["date"], index_col="date")
    assert (total, added) == (3, 1)
    assert result.loc["2026-01-01", "value"] == 1.0
    assert result.loc["2026-01-02", "value"] == 3.0
    assert not list(tmp_path.glob("*.tmp"))
