#!/usr/bin/env python
"""Safely recompute and atomically publish one research snapshot."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from inv.reporting import publish_directory_atomically, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "content" / "_assets" / "plots"
SCRIPTS = ROOT / "scripts" / "research"
CONTRACT_SCRIPT = ROOT / "scripts" / "content-contract.ts"
SAFE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def content_contract(report: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx", str(CONTRACT_SCRIPT), report],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("内容契约必须是对象")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", help="研究 slug")
    args = parser.parse_args()
    report = args.report
    if not SAFE_SLUG.fullmatch(report):
        parser.error("REPORT 只能包含小写字母、数字和单连字符分隔段")

    script = SCRIPTS / f"{report}.py"
    if not script.is_file():
        parser.error(f"缺少分析脚本：{script.relative_to(ROOT)}")
    try:
        contract = content_contract(report)
    except (json.JSONDecodeError, subprocess.CalledProcessError, ValueError) as error:
        parser.error(f"无法读取研究内容契约：{error}")
    data_as_of = contract.get("dataAsOf")
    plots = contract.get("plots")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data_as_of)):
        parser.error(f"content/research/{report}.md 含图表时必须填写 ISO data_as_of")
    if not isinstance(plots, list) or not plots:
        parser.error(f"content/research/{report}.md 没有 PlotlyChart 引用")
    chart_ids = [entry.get("chart") for entry in plots if isinstance(entry, dict)]
    if len(chart_ids) != len(plots) or any(not isinstance(name, str) for name in chart_ids):
        parser.error("研究内容契约中的图表引用无效")

    ASSETS.parent.mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=f".{report}-", dir=ASSETS.parent))
    snapshot = stage_root / report
    env = os.environ.copy()
    env["INV_REPORT_OUTPUT_DIR"] = str(snapshot)
    env["INV_REPORT_SLUG"] = report
    env["INV_REPORT_DATA_AS_OF"] = str(data_as_of)
    env["MPLCONFIGDIR"] = str(stage_root / ".matplotlib")
    try:
        subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, check=True)
        validate_snapshot(
            snapshot,
            report=report,
            data_as_of=str(data_as_of),
            chart_ids=chart_ids,
        )
        publish_directory_atomically(snapshot, ASSETS / report)
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)

    print(f"[analyze] OK: {report} -> {ASSETS.joinpath(report).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
