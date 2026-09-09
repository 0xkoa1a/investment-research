"""CSV 读写、增量合并与网络重试。

设计原则:
  1. data/raw 增量合并 —— 新数据与旧数据按索引合并，新值可更新同日修订值，
     但不会因抓取窗口缩短或失败而清空既有历史。
  2. 所有落盘为 UTF-8 CSV，日期为 ISO 格式（YYYY-MM-DD），
     保证任何工具（Excel/pandas/R/命令行）都能读。
  3. 抓取失败不抛出到顶层，而是记录并返回 None，让批量抓取能继续。
"""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

_ICONS = {"ok": "[ OK ]", "skip": "[SKIP]", "fail": "[FAIL]", "info": "[INFO]", "warn": "[WARN]"}


def log(level: str, msg: str) -> None:
    """统一格式的控制台输出。"""
    print(f"{_ICONS.get(level, '[    ]')} {msg}", flush=True)


# ---------------------------------------------------------------------------
# 重试
# ---------------------------------------------------------------------------


def retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    label: str = "",
) -> T | None:
    """执行 fn，失败则指数退避重试。全部失败返回 None（不抛出）。"""
    wait = delay
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - 网络抓取需要兜住所有异常
            last_err = e
            if i < attempts:
                log("warn", f"{label} 第 {i}/{attempts} 次失败: {type(e).__name__}: {e} —— {wait:.0f}s 后重试")
                time.sleep(wait)
                wait *= backoff
    log("fail", f"{label} 重试 {attempts} 次后仍失败: {type(last_err).__name__}: {last_err}")
    return None


# ---------------------------------------------------------------------------
# 读
# ---------------------------------------------------------------------------


def read_series_csv(path: Path) -> pd.DataFrame | None:
    """读取单序列 CSV（date 索引）。文件不存在返回 None。"""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"], index_col="date")
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log("warn", f"读取 {path.name} 失败: {e}")
        return None


def read_all_in_dir(directory: Path) -> dict[str, pd.DataFrame]:
    """读取目录下所有 CSV，返回 {文件名(不含后缀): DataFrame}。"""
    out: dict[str, pd.DataFrame] = {}
    if not directory.exists():
        return out
    for p in sorted(directory.glob("*.csv")):
        df = read_series_csv(p)
        if df is not None and not df.empty:
            out[p.stem] = df
    return out


# ---------------------------------------------------------------------------
# 写（增量合并）
# ---------------------------------------------------------------------------


def _atomic_to_csv(
    path: Path,
    frame: pd.DataFrame,
    *,
    index_label: str,
) -> None:
    """Write a CSV beside its target, fsync it, then atomically replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.fchmod(descriptor, 0o644)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        frame.to_csv(
            temporary_path,
            encoding="utf-8",
            index_label=index_label,
            date_format="%Y-%m-%d",
        )
        with temporary_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def upsert_csv(path: Path, new: pd.DataFrame) -> tuple[int, int]:
    """将 new 增量合并写入 path。

    合并语义:
      - 索引为日期，同日数据以 new 为准（数据源修订时能更新）。
      - 历史上存在但 new 中缺失的日期予以**保留**（防止抓取窗口缩短造成数据丢失）。

    Returns:
        (合并后总行数, 本次新增行数)
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if new is None or new.empty:
        log("warn", f"{path.name} 传入空数据，跳过写入（保留原文件）")
        old = read_series_csv(path)
        return (len(old) if old is not None else 0, 0)

    new = new.copy()
    new.index = pd.to_datetime(new.index).normalize()
    new.index.name = "date"
    new = new[~new.index.duplicated(keep="last")].sort_index()

    old = read_series_csv(path)
    if old is None or old.empty:
        merged = new
        added = len(new)
    else:
        before = set(old.index)
        # combine_first: new 优先，old 补齐 new 缺失的日期与列
        merged = new.combine_first(old).sort_index()
        added = len(set(merged.index) - before)

    merged.index.name = "date"
    _atomic_to_csv(path, merged, index_label="date")
    return len(merged), added


def write_csv(path: Path, df: pd.DataFrame, *, index_label: str = "date") -> None:
    """全量覆盖写出（用于 data/processed 派生数据）。"""
    _atomic_to_csv(path, df, index_label=index_label)
    log("ok", f"写出 {path.name}  ({len(df)} 行 × {len(df.columns)} 列)")


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def to_single_col(obj: Any, col: str) -> pd.DataFrame | None:
    """把 Series 或单列 DataFrame 规整为列名为 col 的 DataFrame。"""
    if obj is None:
        return None
    if isinstance(obj, pd.Series):
        df = obj.to_frame(name=col)
    elif isinstance(obj, pd.DataFrame):
        if obj.empty:
            return None
        df = obj.iloc[:, [0]].copy()
        df.columns = [col]
    else:
        return None
    df = df.dropna(how="all")
    if df.empty:
        return None
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    return df
