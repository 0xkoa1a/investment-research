#!/usr/bin/env python
"""Collect/verify immutable gold research snapshots; never write report prose."""

from __future__ import annotations

import argparse
from pathlib import Path

from inv.gold_data import build_snapshot, timestamp, verify_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", help="带时区的研究信息截止时间，例如 2026-09-09T11:59:46Z")
    parser.add_argument("--refresh", action="store_true", help="显式联网；默认只读缓存")
    parser.add_argument("--futures-review", action="store_true", help="核验 COMEX 行情并保存独立缓存快照与公开覆盖记录")
    parser.add_argument("--intraday", action="store_true", help="保存独立 Yahoo 五分钟行情快照；固定范围见 config.GOLD_RESEARCH_INTRADAY")
    parser.add_argument("--drivers", action="store_true", help="固定 Phase 2 驱动补充；--refresh 仅更新 DXY / WTI，FedWatch 与 GLD 读取已取得的缓存")
    parser.add_argument("--outlook", action="store_true", help="Phase 4：导入独立更新快照，商业原始数值只存本地忽略缓存")
    parser.add_argument("--research-update", action="store_true", help="新研究周期 Phase 0：下载独立、长期保存的输入，不改报告和图表")
    parser.add_argument("--start", help="--research-update 的重点样本起点，YYYY-MM-DD")
    parser.add_argument("--background-start", default="2023-08-01", help="--research-update 的背景样本起点")
    parser.add_argument("--evidence", type=Path, help="--research-update 的来源核验和实际公布时间记录 JSON")
    parser.add_argument("--sample-end", help="最后完整纽约交易日期，YYYY-MM-DD；新周期采用 Yahoo 日线 Close")
    parser.add_argument("--imports", type=Path, help="导入目录；--outlook 接受既有来源导出，其余模式只接受已确认公开许可的 CSV")
    parser.add_argument("--verify", type=Path, help="只校验已有快照及文件哈希")
    args = parser.parse_args()
    if args.verify:
        if args.cutoff or args.refresh or args.imports or args.futures_review or args.intraday or args.drivers or args.outlook or args.research_update or args.sample_end or args.start or args.evidence:
            parser.error("--verify 不与抓取参数一起使用")
        import json

        from inv import config as C

        selection = json.loads((args.verify / "manifest.json").read_text())
        if selection.get("kind") == "gold-research-refresh":
            from inv.gold_refresh import verify_refresh
            manifest = verify_refresh(args.verify, C.GOLD_RESEARCH_LOCAL)
        else:
            manifest = verify_snapshot(args.verify)
        print(f"[gold-check] OK: {manifest['cutoff_at']}, {len(manifest['files'])} files")
        return 0
    if not args.cutoff:
        parser.error("必须指定 --cutoff 或 --verify")
    if args.research_update:
        if args.futures_review or args.intraday or args.drivers or args.outlook:
            parser.error("--research-update 不与旧阶段模式同用")
        if not args.start or not args.sample_end or not args.evidence or not args.refresh:
            parser.error("--research-update 需要 --start、--sample-end、--evidence 和显式 --refresh")
        from inv import config as C
        from inv.gold_refresh import freeze_refresh

        try:
            path = freeze_refresh(timestamp(args.cutoff), focus_start=args.start,
                                  background_start=args.background_start, sample_end=args.sample_end,
                                  refresh=args.refresh, public_root=C.GOLD_RESEARCH_RAW,
                                  local_root=C.GOLD_RESEARCH_LOCAL, evidence=args.evidence, imports=args.imports)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        import json

        readiness = json.loads((path / "readiness.json").read_text(encoding="utf-8"))
        primary_ready = bool(readiness.get("primary_ready", False))
        print(f"[gold-research-update] {path.relative_to(C.ROOT)}")
        print(f"[gold-research-update] primary_ready={str(primary_ready).lower()}")
        if primary_ready:
            print("[gold-phase-0] 主价格数据已通过准备检查；不授权进入 Phase 1。")
            return 0
        print("[gold-phase-0] 主价格数据未通过准备检查；输入已保留供审查，不授权进入 Phase 1。")
        return 1
    if args.start or args.evidence:
        parser.error("--start 和 --evidence 仅用于 --research-update")
    if args.sample_end and not args.outlook:
        parser.error("--sample-end 仅用于 --outlook 或 --research-update")
    if args.outlook:
        if args.refresh or args.drivers or args.intraday or args.futures_review or not args.imports or not args.sample_end:
            parser.error("--outlook 需要 --imports 和 --sample-end，不与其他模式或 --refresh 同用")
        from inv.gold_update import freeze_update
        try:
            path = freeze_update(timestamp(args.cutoff), args.sample_end, args.imports)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(f"[gold-outlook] {path.relative_to(path.parents[4])}")
        return 0
    if args.drivers:
        if args.imports or args.futures_review or args.intraday:
            parser.error("--drivers 不与其他抓取模式同用")
        from inv.gold_drivers import freeze_drivers
        try:
            path = freeze_drivers(timestamp(args.cutoff), refresh=args.refresh)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(f"[gold-drivers] {path.name}")
        return 0
    if args.intraday:
        if args.imports or args.futures_review:
            parser.error("--intraday 不与 --imports / --futures-review 同用")
        from inv.gold_intraday import freeze_intraday
        try:
            path = freeze_intraday(timestamp(args.cutoff), refresh=args.refresh)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(f"[gold-intraday] {path.name}")
        return 0
    if args.futures_review:
        if args.imports:
            parser.error("--futures-review 不与 --imports 同用")
        from inv.gold_futures import review_futures
        try:
            path = review_futures(timestamp(args.cutoff), refresh=args.refresh)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(f"[gold-futures-review] {path.relative_to(path.parents[4])}")
        print("[gold-phase-0] 已选 COMEX 期货；接续、Close 口径及公开使用条件仍需核验。")
        return 0
    try:
        path = build_snapshot(timestamp(args.cutoff), refresh=args.refresh, imports=args.imports)
        manifest = verify_snapshot(path)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    failed = [r['series'] for r in manifest['series'] if r['status'] == 'failed']
    print(f"[gold-snapshot] {path.name}; downloaded={sum(bool(r['file']) for r in manifest['series'])}; failed={failed}")
    print("[gold-phase-0] 主研究对象为 COMEX 期货；行情核验见 --futures-review。此命令不授权进入 Phase 1。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
