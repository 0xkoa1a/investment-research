#!/usr/bin/env python
"""一键抓取全部数据源。

用法:
    uv run python scripts/update_all.py                # 增量更新（近 5 年）
    uv run python scripts/update_all.py --full         # 全量重抓（1990 起）
    uv run python scripts/update_all.py --only fred    # 仅抓 FRED
    uv run python scripts/update_all.py --no-build     # 抓完不重建数据集

设计说明:
  - 各数据源相互独立，单一数据源失败不影响其他源。
  - 默认只抓近 5 年（增量场景足够且快）；首次使用请加 --full。
  - 抓取完成后自动重建数据集与 SOURCES.md。
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

from inv import config as C
from inv.storage import log

SOURCES = ("fred", "market", "cn")


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取全部投资研究数据源")
    ap.add_argument("--full", action="store_true", help=f"全量重抓（自 {C.START_DATE}）")
    ap.add_argument("--years", type=int, default=5, help="增量模式回溯年数（默认 5）")
    ap.add_argument("--only", nargs="+", choices=SOURCES, help="仅抓取指定数据源")
    ap.add_argument("--no-build", action="store_true", help="抓取后不重建数据集")
    ap.add_argument("--allow-partial", action="store_true", help="明确接受部分抓取失败并使用保留的旧数据继续构建")
    args = ap.parse_args()

    if args.full:
        start = C.START_DATE
    else:
        start = (date.today() - timedelta(days=365 * args.years + 10)).isoformat()

    sources = args.only or list(SOURCES)
    C.ensure_dirs()

    log("info", "=" * 66)
    log("info", f"数据更新开始  start={start}  sources={', '.join(sources)}")
    log("info", "=" * 66)

    t0 = time.time()
    summary: dict[str, int] = {}
    expected: dict[str, int] = {}

    if "fred" in sources:
        from inv import fetch_fred

        print()
        summary["FRED"] = len(fetch_fred.fetch_all(start=start))
        expected["FRED"] = len(C.FRED_SERIES)

    if "market" in sources:
        from inv import fetch_market

        print()
        summary["Yahoo Finance"] = len(fetch_market.fetch_all(start=start))
        expected["Yahoo Finance"] = len(C.YF_TICKERS)

    if "cn" in sources:
        from inv import fetch_cn

        print()
        summary["A股"] = len(fetch_cn.fetch_all(start=start))
        expected["A股"] = len(C.CN_INDEXES)

    print()
    log("info", "=" * 66)
    for k, v in summary.items():
        level = "ok" if v == expected[k] else "fail"
        log(level, f"{k:<16} {v}/{expected[k]} 个序列")
    log("info", f"抓取耗时 {time.time() - t0:.1f}s")
    log("info", "=" * 66)

    incomplete = {name: (summary[name], expected[name]) for name in summary if summary[name] != expected[name]}
    if incomplete and not args.allow_partial:
        log("fail", f"数据更新不完整，保留已有文件且不重建派生数据：{incomplete}")
        log("info", "确认接受旧数据时可显式添加 --allow-partial")
        return 1

    if not args.no_build:
        print()
        from inv import dataset

        if not dataset.build():
            return 1

        print()
        from inv import sources

        sources.generate()

    return 0


if __name__ == "__main__":
    sys.exit(main())
