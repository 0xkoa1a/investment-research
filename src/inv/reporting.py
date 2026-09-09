"""Versioned Plotly snapshots and atomic publication helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SAFE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_payload(payload: object, name: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError(f"Plotly JSON 必须是对象：{name}")
    data = payload.get("data")
    layout = payload.get("layout")
    if not isinstance(data, list) or not isinstance(layout, dict):
        raise ValueError(f"Plotly JSON 必须包含 data 数组与 layout 对象：{name}")
    if "title" in layout or "height" in layout:
        raise ValueError(f"Plotly JSON 不允许标题或固定高度：{name}")
    if set(payload) != {"data", "layout"}:
        raise ValueError(f"Plotly JSON 只允许 data 与 layout：{name}")
    return {"data": data, "layout": layout}


def validate_snapshot(
    snapshot: Path,
    *,
    report: str,
    data_as_of: str,
    chart_ids: Iterable[str],
) -> None:
    """Validate a staged snapshot before it can replace the committed copy."""
    if not SAFE_SLUG.fullmatch(report):
        raise ValueError(f"研究 slug 无效：{report}")
    expected_ids = list(chart_ids)
    if not expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise ValueError("正文必须引用至少一个且不重复的图表")
    if any(not SAFE_SLUG.fullmatch(name) for name in expected_ids):
        raise ValueError("正文包含不安全图表 ID")

    manifest_path = snapshot / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("研究脚本未生成 manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest 必须是对象")
    if manifest.get("report") != report:
        raise ValueError("manifest.report 与 REPORT 不一致")
    if str(manifest.get("data_as_of")) != data_as_of:
        raise ValueError("manifest.data_as_of 与研究正文不一致")
    charts = manifest.get("charts")
    if not isinstance(charts, list) or not charts:
        raise ValueError("manifest.charts 必须是非空数组")

    manifest_files: list[str] = []
    for entry in charts:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ValueError("manifest.charts 条目无效")
        filename = entry["file"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*\.json", filename):
            raise ValueError(f"manifest 包含不安全文件名：{filename}")
        if filename in manifest_files:
            raise ValueError(f"manifest 包含重复文件：{filename}")
        manifest_files.append(filename)
        chart_path = snapshot / filename
        if not chart_path.is_file():
            raise ValueError(f"manifest 引用缺失文件：{filename}")
        payload = json.loads(chart_path.read_text(encoding="utf-8"))
        _validate_payload(payload, filename)
        digest = hashlib.sha256(chart_path.read_bytes()).hexdigest()
        if entry.get("sha256") != digest:
            raise ValueError(f"manifest 哈希不匹配：{filename}")

    expected_files = sorted(f"{name}.json" for name in expected_ids)
    if sorted(manifest_files) != expected_files:
        raise ValueError(f"正文与 manifest 不一致：正文={expected_files} manifest={sorted(manifest_files)}")
    actual_files = sorted(path.name for path in snapshot.iterdir() if path.is_file())
    allowed_files = sorted(["manifest.json", *expected_files])
    if actual_files != allowed_files:
        raise ValueError(f"快照目录含未声明文件：actual={actual_files} expected={allowed_files}")
    if any(path.is_dir() for path in snapshot.iterdir()):
        raise ValueError("快照目录不允许子目录")


def publish_directory_atomically(snapshot: Path, target: Path) -> None:
    """Replace one snapshot directory while retaining rollback on failure."""
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
        os.replace(snapshot, target)
    except Exception:
        if had_target and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


class ReportWriter:
    """Write canonical Plotly ``{data, layout}`` JSON and a manifest."""

    def __init__(self, report: str | None = None, *, data_as_of: str | None = None) -> None:
        output = os.environ.get("INV_REPORT_OUTPUT_DIR", "").strip()
        if not output:
            raise RuntimeError("INV_REPORT_OUTPUT_DIR 未设置；请通过 make analyze 运行研究脚本")
        self.report = (report or os.environ.get("INV_REPORT_SLUG", "")).strip()
        self.data_as_of = (data_as_of or os.environ.get("INV_REPORT_DATA_AS_OF", "")).strip()
        if not SAFE_SLUG.fullmatch(self.report):
            raise ValueError("研究 slug 无效；请通过 make analyze REPORT=<slug> 运行")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.data_as_of):
            raise ValueError("研究脚本必须通过研究 frontmatter 提供 data_as_of")
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self._charts: list[dict[str, Any]] = []
        self._names: set[str] = set()
        self._finished = False

    def write_plotly(self, figure: Any, name: str) -> Path:
        if self._finished:
            raise RuntimeError("manifest 已完成，不能继续写图")
        if not SAFE_SLUG.fullmatch(name):
            raise ValueError(f"图表名不安全：{name!r}")
        if name in self._names:
            raise ValueError(f"图表名重复：{name}")
        payload = json.loads(figure.to_json())
        if not isinstance(payload, dict):
            raise ValueError(f"Plotly 图表结构无效：{name}")
        layout = payload.get("layout")
        if isinstance(layout, dict):
            layout.pop("title", None)
            layout.pop("height", None)
        normalized = _validate_payload({"data": payload.get("data"), "layout": layout}, name)
        encoded = (json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        output = self.output / f"{name}.json"
        output.write_bytes(encoded)
        self._names.add(name)
        self._charts.append(
            {
                "file": output.name,
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "traces": len(normalized["data"]),
            }
        )
        return output

    def finish(self) -> Path:
        if self._finished:
            raise RuntimeError("manifest 已经生成")
        if not self._charts:
            raise ValueError(f"{self.report}: 没有生成任何 Plotly 图表")
        manifest = {
            "report": self.report,
            "data_as_of": self.data_as_of,
            "charts": sorted(self._charts, key=lambda item: item["file"]),
        }
        output = self.output / "manifest.json"
        output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._finished = True
        return output
