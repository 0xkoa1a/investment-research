from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from inv.reporting import ReportWriter, publish_directory_atomically, validate_snapshot


def write_snapshot(directory: Path, *, title: bool = False, extra: bool = False) -> None:
    directory.mkdir()
    payload = {"data": [{"x": [1], "y": [2]}], "layout": {}}
    if title:
        payload["layout"]["title"] = "forbidden"
    encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
    (directory / "chart.json").write_bytes(encoded)
    manifest = {
        "report": "report",
        "data_as_of": "2026-01-01",
        "charts": [{"file": "chart.json", "sha256": hashlib.sha256(encoded).hexdigest(), "traces": 1}],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if extra:
        (directory / "extra.json").write_text("{}", encoding="utf-8")


def test_snapshot_contract_rejects_layout_and_extra_files(tmp_path: Path) -> None:
    valid = tmp_path / "valid"
    write_snapshot(valid)
    validate_snapshot(valid, report="report", data_as_of="2026-01-01", chart_ids=["chart"])

    titled = tmp_path / "titled"
    write_snapshot(titled, title=True)
    with pytest.raises(ValueError, match="标题或固定高度"):
        validate_snapshot(titled, report="report", data_as_of="2026-01-01", chart_ids=["chart"])

    extra = tmp_path / "extra"
    write_snapshot(extra, extra=True)
    with pytest.raises(ValueError, match="未声明文件"):
        validate_snapshot(extra, report="report", data_as_of="2026-01-01", chart_ids=["chart"])


def test_atomic_publish_replaces_only_after_complete_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "target"
    snapshot = tmp_path / "snapshot"
    target.mkdir()
    snapshot.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    (snapshot / "new.txt").write_text("new", encoding="utf-8")
    publish_directory_atomically(snapshot, target)
    assert not (target / "old.txt").exists()
    assert (target / "new.txt").read_text(encoding="utf-8") == "new"


class FakeFigure:
    def to_json(self) -> str:
        return json.dumps({"data": [], "layout": {"title": "drop", "height": 99}})


def test_report_writer_rejects_duplicate_chart_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INV_REPORT_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("INV_REPORT_SLUG", "report")
    monkeypatch.setenv("INV_REPORT_DATA_AS_OF", "2026-01-01")
    writer = ReportWriter()
    writer.write_plotly(FakeFigure(), "chart")
    with pytest.raises(ValueError, match="重复"):
        writer.write_plotly(FakeFigure(), "chart")
    payload = json.loads((tmp_path / "output" / "chart.json").read_text(encoding="utf-8"))
    assert "title" not in payload["layout"]
    assert "height" not in payload["layout"]
