"""reddit-watch lane collector."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..core import RunContext, RunResult, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..runtime.run_manifest import write_run_manifest
from ..signals.index import write_index
from ..signals.writer import write_signal
from ..sources.reddit_public import RedditPublicError, RedditThread, fetch_reddit_threads
from .registry import register_lane


def _build_signal(ctx: RunContext, query: str, thread: RedditThread) -> SignalRecord:
    filename = f"r__{thread.subreddit}__{thread.thread_id}__reddit_thread__{ctx.date}.md"
    file_path = str(ctx.signals_dir / filename)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    body_text = thread.body or thread.title
    if len(body_text) > 2000:
        body_text = body_text[:2000].rstrip() + "…"
    top_comments_text = "\n\n".join(f"- {comment}" for comment in thread.top_comments)
    record = SignalRecord(
        lane="reddit-watch",
        signal_type="reddit_thread",
        source="reddit",
        entity_type="thread",
        entity_id=thread.thread_id,
        title=thread.title,
        source_url=thread.url,
        fetched_at=fetched_at,
        file_path=file_path,
        handle=thread.author,
        post_id=thread.thread_id,
        created_at=thread.created_at,
        text_preview=body_text,
        likes=thread.score,
        replies=thread.num_comments,
        group=f"r/{thread.subreddit}" if thread.subreddit else "reddit",
        top_comments_text=top_comments_text,
        query=query,
    )
    write_signal(record)
    return record


def collect_reddit_watch(ctx: RunContext) -> RunResult:
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    lane_config = ctx.config.get("lanes", {}).get("reddit-watch", {})
    queries = [q.strip() for q in lane_config.get("queries", []) if isinstance(q, str) and q.strip()]
    if not queries:
        ctx.errors.append("reddit-watch requires a non-empty 'queries' list")
        return _finalize(ctx, started_at, [], 0)

    lookback_days = int(lane_config.get("lookback_days", 30))
    max_threads = int(lane_config.get("max_threads", 10))
    max_per_query = int(lane_config.get("max_per_query", max_threads))
    subreddits = [s.strip() for s in lane_config.get("subreddits", []) if isinstance(s, str) and s.strip()]

    ctx.ensure_dirs()
    all_records: list[SignalRecord] = []
    seen_thread_ids: set[str] = set()
    queries_checked = 0

    for query in queries:
        queries_checked += 1
        debug_log(f"[reddit-watch] query={query}", log_file=ctx.debug_log_path)
        try:
            threads = fetch_reddit_threads(
                query,
                lookback_days=lookback_days,
                max_threads=max_threads,
                subreddits=subreddits or None,
            )
        except RedditPublicError as exc:
            debug_log(f"[reddit-watch] query failed: {query}: {exc}", log_file=ctx.debug_log_path)
            ctx.errors.append(f"query '{query}' failed: {exc}")
            continue

        written_for_query = 0
        for thread in threads:
            if thread.thread_id in seen_thread_ids:
                continue
            seen_thread_ids.add(thread.thread_id)
            try:
                record = _build_signal(ctx, query, thread)
                all_records.append(record)
                written_for_query += 1
                debug_log(
                    f"[reddit-watch] + {thread.thread_id} r/{thread.subreddit} score={thread.score} comments={thread.num_comments}",
                    log_file=ctx.debug_log_path,
                )
            except Exception as exc:
                debug_log(f"[reddit-watch] failed to write thread {thread.thread_id}: {exc}", log_file=ctx.debug_log_path)
                ctx.errors.append(f"failed to write thread {thread.thread_id}: {exc}")
            if written_for_query >= max_per_query:
                break

    return _finalize(ctx, started_at, all_records, queries_checked)


def _finalize(ctx: RunContext, started_at: str, records: list[SignalRecord], queries_checked: int) -> RunResult:
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    signal_types_count: dict[str, int] = {}
    for record in records:
        signal_types_count[record.signal_type] = signal_types_count.get(record.signal_type, 0) + 1

    status = RunStatus.SUCCESS if records else RunStatus.EMPTY
    if ctx.errors:
        status = RunStatus.FAILED

    result = RunResult(
        lane="reddit-watch",
        date=ctx.date,
        status=status,
        started_at=started_at,
        session_id=None,
        finished_at=finished_at,
        warnings=ctx.warnings,
        errors=ctx.errors,
        signal_records=records,
        repos_checked=queries_checked,
        signals_written=len(records),
        signal_types_count=signal_types_count,
        index_file=str(ctx.index_path),
    )
    _write_index_to_file(result, ctx.index_path)
    _write_manifest_to_file(result, ctx.run_json_path)
    debug_log(f"[reddit-watch] END signals={len(records)} queries={queries_checked}", log_file=ctx.debug_log_path)
    return result


def _write_index_to_file(result: RunResult, index_path: Path) -> bool:
    try:
        write_index(result, index_path)
        return True
    except Exception as exc:
        result.errors.append(f"failed to write index.md: {exc}")
        result.status = RunStatus.FAILED
        return False


def _write_manifest_to_file(result: RunResult, run_json_path: Path) -> bool:
    try:
        write_run_manifest(result, run_json_path)
        return True
    except Exception as exc:
        result.errors.append(f"failed to write run.json: {exc}")
        result.status = RunStatus.FAILED
        return False


register_lane("reddit-watch", collect_reddit_watch)
