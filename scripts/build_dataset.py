#!/usr/bin/env python
"""重建派生数据集（日/周/月频）。

用法:
    uv run python scripts/build_dataset.py
    uv run python scripts/build_dataset.py --report   # 额外打印字段覆盖率报告

不联网，仅基于 data/raw 下已有数据重新计算。
安全操作：随时可重跑，raw 数据不会被修改。
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from inv import dataset, sources
from inv.storage import log


def coverage_report(df: pd.DataFrame, *, top_missing: int = 15) -> None:
    """打印字段覆盖率，帮助发现抓取失败或数据源失效的字段。"""
    total = len(df)
    cov = df.notna().sum().div(total).sort_values()

    print()
    log("info", f"字段覆盖率报告（共 {len(df.columns)} 列 / {total} 行）")
    print()
    print(f"  {'字段':<24} {'覆盖率':>8}  {'最新有效日期':>12}")
    print("  " + "-" * 50)
    for col in cov.index[:top_missing]:
        last = df[col].last_valid_index()
        last_s = last.date().isoformat() if last is not None else "无数据"
        flag = " <-- 关注" if cov[col] < 0.3 else ""
        print(f"  {col:<24} {cov[col]:>7.1%}  {last_s:>12}{flag}")
    print()
    log("info", f"覆盖率 100% 的字段: {(cov >= 0.999).sum()} 个")

    # 季频数据（GDP）天然更新缓慢，用更宽的阈值避免误报
    LOW_FREQ = {"gdp_real"}
    stale = []
    for c in df.columns:
        lv = df[c].last_valid_index()
        if lv is None:
            continue
        limit = 200 if c.replace("ret_", "").replace("d_", "") in LOW_FREQ else 60
        if (df.index.max() - lv).days > limit:
            stale.append(c)
    if stale:
        log("warn", f"更新滞后的字段（可能数据源已失效）: {', '.join(stale[:10])}")


def main() -> int:
    ap = argparse.ArgumentParser(description="重建派生数据集")
    ap.add_argument("--report", action="store_true", help="打印字段覆盖率报告")
    ap.add_argument("--no-sources", action="store_true", help="不重新生成 SOURCES.md")
    args = ap.parse_args()

    out = dataset.build()
    if not out:
        return 1

    if args.report:
        coverage_report(out["daily"])

    if not args.no_sources:
        print()
        sources.generate()

    return 0


if __name__ == "__main__":
    sys.exit(main())
