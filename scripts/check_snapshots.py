#!/usr/bin/env python
"""Validate all committed Plotly snapshots against the canonical content contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from inv.reporting import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "content" / "_assets" / "plots"


def contracts() -> list[dict[str, object]]:
    result = subprocess.run(
        ["node", "--import", "tsx", "scripts/content-contract.ts", "--all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, list):
        raise ValueError("内容契约列表无效")
    return [item for item in value if isinstance(item, dict)]


def main() -> int:
    errors: list[str] = []
    try:
        values = contracts()
    except (json.JSONDecodeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"[snapshot-check] FAIL: 无法读取内容契约：{error}")
        return 1
    checked = 0
    for contract in values:
        plots = contract.get("plots")
        if not isinstance(plots, list) or not plots:
            continue
        slug = str(contract.get("slug", ""))
        data_as_of = str(contract.get("dataAsOf", ""))
        chart_ids = [str(plot.get("chart", "")) for plot in plots if isinstance(plot, dict)]
        try:
            validate_snapshot(
                ASSETS / slug,
                report=slug,
                data_as_of=data_as_of,
                chart_ids=chart_ids,
            )
            checked += 1
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"{slug}: {error}")
    if errors:
        for error in errors:
            print(f"[snapshot-check] FAIL: {error}")
        return 1
    print(f"[snapshot-check] OK: {checked} 份研究快照")
    return 0


if __name__ == "__main__":
    sys.exit(main())
