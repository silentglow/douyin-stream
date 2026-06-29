#!/usr/bin/env python3
"""一次性清理千问账号端的孤儿 recordId。

历史背景 v2026-05-26：
  在 fix(5727161) 之前，flow.py 上传/转写失败时不清理已分配的 recordId,
  这些 recordId 留在千问账号"记录"列表里变孤儿(`重试` `失败` `上传中`等状态)。
  本脚本扫描 data/logs/media_tools_*.log,定位孤儿,按账号分组,调 delete_record 清掉。

判定孤儿:
  1. 提取 [filename] recordId: X 行 → 候选 recordId
  2. 同一 filename 后续出现 'md saved:' 行 → 该 filename 的最后一个 recordId 被本次成功清理
     (其余该 filename 的 recordId 仍是孤儿)
  3. 'delete status: success' 行单独存在但只对应当前 attempt 的 recordId,
     已经在 (2) 涵盖

账号定位:
  按 recordId 时间戳之后最近的 '保留在账号 X 的重试链路' WARNING 行抓 account_id。
  失败抓不到的退到 transcribe_runs 表按 filename 反查;再失败标记 <unknown> 跳过。

用法:
  python scripts/cleanup_orphan_qwen_records.py            # dry-run,只打印
  python scripts/cleanup_orphan_qwen_records.py --apply    # 实际执行 delete_record
  python scripts/cleanup_orphan_qwen_records.py --logs data/logs --days 7
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

# 让脚本能 import src/
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


RE_RECORD_ALLOC = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
    r"\[([^\[\]]+?)\] recordId: ([a-f0-9-]{36})"
)
RE_MD_SAVED = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
    r"\[([^\[\]]+?)\] (?:md|docx|pdf|srt|txt) saved:"
)
RE_DELETE_SUCCESS = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
    r"\[([^\[\]]+?)\] delete status: success"
)
RE_ACCOUNT_FAIL = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
    r"保留在账号 ([a-f0-9-]+) 的重试链路"
)
# ERROR 行带完整文件路径,用来配对账号 ID
RE_MAX_ATTEMPTS_ERROR = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
    r"已达最大尝试次数 \(\d+\): (.+?\.(?:mp4|mov|m4a|mp3|wav|flac|aac))"
)

TS_FMT = "%Y-%m-%d %H:%M:%S"


@dataclass
class RecordEvent:
    ts: datetime
    filename: str
    record_id: str


@dataclass
class AccountEvent:
    ts: datetime
    account_id: str


@dataclass
class SuccessEvent:
    ts: datetime
    filename: str


@dataclass
class MaxAttemptsError:
    ts: datetime
    filename: str  # 文件名(不含路径)


def parse_log_file(
    path: Path,
) -> tuple[list[RecordEvent], list[SuccessEvent], list[AccountEvent], list[MaxAttemptsError]]:
    records: list[RecordEvent] = []
    successes: list[SuccessEvent] = []
    account_fails: list[AccountEvent] = []
    max_errors: list[MaxAttemptsError] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"  ! 无法读取 {path}: {exc}", file=sys.stderr)
        return records, successes, account_fails, max_errors
    for line in text.splitlines():
        if m := RE_RECORD_ALLOC.search(line):
            ts = datetime.strptime(m.group(1), TS_FMT)
            records.append(RecordEvent(ts=ts, filename=m.group(2), record_id=m.group(3)))
            continue
        if m := RE_MD_SAVED.search(line):
            ts = datetime.strptime(m.group(1), TS_FMT)
            successes.append(SuccessEvent(ts=ts, filename=m.group(2)))
            continue
        if m := RE_DELETE_SUCCESS.search(line):
            ts = datetime.strptime(m.group(1), TS_FMT)
            successes.append(SuccessEvent(ts=ts, filename=m.group(2)))
            continue
        if m := RE_ACCOUNT_FAIL.search(line):
            ts = datetime.strptime(m.group(1), TS_FMT)
            account_fails.append(AccountEvent(ts=ts, account_id=m.group(2)))
            continue
        if m := RE_MAX_ATTEMPTS_ERROR.search(line):
            ts = datetime.strptime(m.group(1), TS_FMT)
            full_path = m.group(2)
            filename = Path(full_path).name
            max_errors.append(MaxAttemptsError(ts=ts, filename=filename))
    return records, successes, account_fails, max_errors


def _pair_account_failures_with_filenames(
    account_fails: list[AccountEvent],
    max_errors: list[MaxAttemptsError],
    pair_window_seconds: int = 5,
) -> dict[str, list[tuple[datetime, str]]]:
    """把 '保留在账号 X' 行和紧邻的 '已达最大尝试次数 (\\d+): /path/<filename>' 行配对。
    返回 {filename: [(ts, account_id), ...]}, 按时间排序。"""
    pairings: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    sorted_accounts = sorted(account_fails, key=lambda a: a.ts)
    used_accounts: set[int] = set()
    for err in max_errors:
        # 找 err 之前(或同秒)且最近的、未配对的 account_fail
        best_idx: int | None = None
        best_dt: timedelta | None = None
        for idx, acc in enumerate(sorted_accounts):
            if idx in used_accounts:
                continue
            if acc.ts > err.ts:
                break
            dt = err.ts - acc.ts
            if dt > timedelta(seconds=pair_window_seconds):
                continue
            if best_dt is None or dt < best_dt:
                best_dt = dt
                best_idx = idx
        if best_idx is not None:
            used_accounts.add(best_idx)
            pairings[err.filename].append((err.ts, sorted_accounts[best_idx].account_id))
    for filename in pairings:
        pairings[filename].sort(key=lambda x: x[0])
    return pairings


def _lookup_account_from_db(filename: str, db_path: Path) -> str | None:
    """从 transcribe_runs 反查 account_id (按 filename 在 video_path 内)。"""
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT account_id FROM transcribe_runs "
                "WHERE video_path LIKE ? ORDER BY updated_at DESC LIMIT 1",
                (f"%{filename}%",),
            ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def attribute_to_account(
    record: RecordEvent,
    pairings_by_file: dict[str, list[tuple[datetime, str]]],
    successes_by_file: dict[str, list[datetime]],
    db_path: Path,
    max_attribution_minutes: int = 30,
) -> str:
    """优先用 filename 配对的账号 ID,失败退到 DB 反查。
    返回 '<cleaned>' 表示该 recordId 已经在成功路径里清掉。"""
    cutoff = record.ts + timedelta(minutes=max_attribution_minutes)
    # 如果该 filename 在 recordId 之后还有 md saved 事件, 那次成功的 recordId 是这个
    succ_times = successes_by_file.get(record.filename, [])
    succ_after = [t for t in succ_times if record.ts <= t <= cutoff]
    if succ_after:
        return "<cleaned>"
    # 优先：filename 配对的失败,取 recordId 时间后最近的一条
    file_pairs = pairings_by_file.get(record.filename, [])
    for ts, account_id in file_pairs:
        if record.ts <= ts <= cutoff:
            return account_id
    # fallback: DB 查
    fallback = _lookup_account_from_db(record.filename, db_path)
    return fallback or "<unknown>"


def find_orphans(
    log_dir: Path,
    days: int,
    db_path: Path,
) -> dict[str, list[tuple[str, str]]]:
    """返回 {account_id: [(filename, record_id), ...]}, 不含 <cleaned>。"""
    cutoff_date = datetime.now() - timedelta(days=days)
    all_records: list[RecordEvent] = []
    all_successes: list[SuccessEvent] = []
    all_account_fails: list[AccountEvent] = []
    all_max_errors: list[MaxAttemptsError] = []

    log_files = sorted(log_dir.glob("media_tools_*.log"))
    if not log_files:
        print(f"未在 {log_dir} 找到 media_tools_*.log", file=sys.stderr)
        return {}

    for log_file in log_files:
        recs, succs, accs, errs = parse_log_file(log_file)
        all_records.extend(recs)
        all_successes.extend(succs)
        all_account_fails.extend(accs)
        all_max_errors.extend(errs)

    all_records = [r for r in all_records if r.ts >= cutoff_date]
    all_successes = [s for s in all_successes if s.ts >= cutoff_date]
    all_account_fails = [a for a in all_account_fails if a.ts >= cutoff_date]
    all_max_errors = [e for e in all_max_errors if e.ts >= cutoff_date]

    pairings_by_file = _pair_account_failures_with_filenames(all_account_fails, all_max_errors)

    successes_by_file: dict[str, list[datetime]] = defaultdict(list)
    for s in all_successes:
        successes_by_file[s.filename].append(s.ts)

    # 同一 filename 成功后, 最近的一个 recordId 已经被 delete_record 清掉;
    # 但 filename 还可能有更早的孤儿 recordId(失败的 attempt)。
    cleaned_record_ids: set[str] = set()
    for filename, succ_times in successes_by_file.items():
        for succ_ts in succ_times:
            window_records = [
                r for r in all_records
                if r.filename == filename and r.ts <= succ_ts
            ]
            if window_records:
                cleaned_record_ids.add(max(window_records, key=lambda r: r.ts).record_id)

    orphans_by_account: dict[str, list[tuple[str, str]]] = defaultdict(list)
    seen_record_ids: set[str] = set()
    for record in all_records:
        if record.record_id in seen_record_ids:
            continue
        seen_record_ids.add(record.record_id)
        if record.record_id in cleaned_record_ids:
            continue
        account_id = attribute_to_account(
            record, pairings_by_file, successes_by_file, db_path,
        )
        if account_id == "<cleaned>":
            continue
        orphans_by_account[account_id].append((record.filename, record.record_id))
    return orphans_by_account


async def delete_orphans_for_account(
    account_id: str,
    record_ids: list[str],
    batch_size: int = 20,
) -> tuple[int, int]:
    """返回 (ok_count, fail_count)。"""
    from media_tools.accounts.auth_state import resolve_qwen_cookie_string
    from media_tools.accounts.db_account_pool import (
        build_qwen_auth_state_path_for_account,
    )
    from media_tools.common.http import RequestsApiContext
    from media_tools.transcribe.flow import delete_record

    auth_state_path = build_qwen_auth_state_path_for_account(account_id)
    if not auth_state_path.exists():
        print(f"  ! 账号 {account_id} auth_state 不存在: {auth_state_path}", file=sys.stderr)
        return 0, len(record_ids)

    cookie_string = resolve_qwen_cookie_string(
        auth_state_path=auth_state_path, account_id=account_id
    )
    if not cookie_string.strip():
        print(f"  ! 账号 {account_id} cookie 为空", file=sys.stderr)
        return 0, len(record_ids)

    api = RequestsApiContext(cookie_string=cookie_string)
    ok = 0
    fail = 0
    try:
        for i in range(0, len(record_ids), batch_size):
            batch = record_ids[i:i + batch_size]
            try:
                success = await delete_record(api, batch)
                if success:
                    ok += len(batch)
                    print(f"  ✓ 批 {i // batch_size + 1}: 清掉 {len(batch)} 条 recordId")
                else:
                    fail += len(batch)
                    print(f"  ✗ 批 {i // batch_size + 1}: delete_record 返回 False")
            except Exception as exc:
                fail += len(batch)
                print(f"  ✗ 批 {i // batch_size + 1}: {exc}")
    finally:
        await api.dispose()
    return ok, fail


async def main_async(args: argparse.Namespace) -> int:
    log_dir = Path(args.logs).resolve()
    db_path = Path(args.db).resolve()

    if not log_dir.is_dir():
        print(f"日志目录不存在: {log_dir}", file=sys.stderr)
        return 2

    orphans_by_account = find_orphans(log_dir, args.days, db_path)
    if not orphans_by_account:
        print("未发现孤儿 recordId。")
        return 0

    total = sum(len(v) for v in orphans_by_account.values())
    print(f"\n发现 {total} 个孤儿 recordId,分布在 {len(orphans_by_account)} 个账号:\n")
    for account_id in sorted(orphans_by_account.keys()):
        items = orphans_by_account[account_id]
        print(f"  账号 {account_id}: {len(items)} 个孤儿")
        for filename, record_id in items[:10]:
            print(f"    {record_id}  ← {filename}")
        if len(items) > 10:
            print(f"    ... 还有 {len(items) - 10} 个")

    if not args.apply:
        print("\n[dry-run] 加 --apply 实际执行 delete_record。")
        return 0

    if "<unknown>" in orphans_by_account:
        print(
            f"\n! 有 {len(orphans_by_account['<unknown>'])} 个孤儿账号未知,跳过。"
            f"如需处理,请先补 transcribe_runs 或手动指定账号。"
        )

    total_ok = 0
    total_fail = 0
    for account_id, items in sorted(orphans_by_account.items()):
        if account_id == "<unknown>":
            continue
        print(f"\n>>> 清理账号 {account_id} 的 {len(items)} 个孤儿...")
        record_ids = [r for _, r in items]
        ok, fail = await delete_orphans_for_account(account_id, record_ids)
        total_ok += ok
        total_fail += fail

    print(f"\n完成: 成功 {total_ok}, 失败 {total_fail}")
    return 0 if total_fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default="data/logs", help="日志目录 (默认 data/logs)")
    ap.add_argument("--db", default="data/media_tools.db", help="SQLite 数据库路径")
    ap.add_argument("--days", type=int, default=7, help="扫描最近 N 天的日志 (默认 7)")
    ap.add_argument("--apply", action="store_true", help="实际执行删除(否则只 dry-run)")
    args = ap.parse_args()

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
