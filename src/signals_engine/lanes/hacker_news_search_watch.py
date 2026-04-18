"""hacker-news-search-watch lane collector."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..core import RunContext, RunResult, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..runtime.run_manifest import write_run_manifest
from ..signals.index import write_index
from ..signals.writer import write_signal
from ..sources.hackernews import HackerNewsError, HackerNewsStory, fetch_hackernews_search_stories
from .registry import register_lane


def _parse_positive_int(value: object, *, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"hacker-news-search-watch '{field_name}' must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"hacker-news-search-watch '{field_name}' must be a positive integer")
    return parsed


def _parse_bool(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError(f"hacker-news-search-watch '{field_name}' must be a boolean")


def _build_signal(ctx: RunContext, story: HackerNewsStory) -> SignalRecord:
    filename = f"hn__search__{story.story_id}__story__{ctx.date}.md"
    file_path = str(ctx.signals_dir / filename)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    top_comments_text = "\n\n".join(f"- {comment}" for comment in story.top_comments)
    record = SignalRecord(
        lane="hacker-news-search-watch",
        signal_type="hackernews_story_search_hit",
        source="hackernews",
        entity_type="story",
        entity_id=str(story.story_id),
        title=story.title,
        source_url=story.discussion_url,
        fetched_at=fetched_at,
        file_path=file_path,
        handle=story.author,
        post_id=str(story.story_id),
        created_at=story.created_at,
        position=story.position,
        text_preview=story.text_preview,
        likes=story.score,
        replies=story.descendants,
        group=story.story_list_name,
        top_comments_text=top_comments_text,
        external_url=story.external_url,
        query=story.query,
    )
    write_signal(record)
    return record


def collect_hacker_news_search_watch(ctx: RunContext) -> RunResult:
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    lane_config = ctx.config.get("lanes", {}).get("hacker-news-search-watch", {})
    if not isinstance(lane_config, dict):
        ctx.errors.append("hacker-news-search-watch config must be a mapping")
        return _finalize(ctx, started_at, [], 0)

    queries = [q.strip() for q in lane_config.get("queries", []) if isinstance(q, str) and q.strip()]
    if not queries:
        ctx.errors.append("hacker-news-search-watch requires a non-empty 'queries' list")
        return _finalize(ctx, started_at, [], 0)

    try:
        max_hits_per_query = _parse_positive_int(
            lane_config.get("max_hits_per_query", 5),
            field_name="max_hits_per_query",
        )
        fetch_top_comments = _parse_bool(
            lane_config.get("fetch_top_comments", True),
            field_name="fetch_top_comments",
        )
        max_top_comments = _parse_positive_int(
            lane_config.get("max_top_comments", 3),
            field_name="max_top_comments",
        )
    except ValueError as exc:
        ctx.errors.append(str(exc))
        return _finalize(ctx, started_at, [], len(queries))

    ctx.ensure_dirs()
    debug_log(
        (
            "[hacker-news-search-watch] START "
            f"queries={len(queries)} max_hits_per_query={max_hits_per_query} "
            f"fetch_top_comments={fetch_top_comments} max_top_comments={max_top_comments}"
        ),
        log_file=ctx.debug_log_path,
    )

    try:
        stories = fetch_hackernews_search_stories(
            queries=queries,
            max_hits_per_query=max_hits_per_query,
            fetch_top_comments=fetch_top_comments,
            max_top_comments=max_top_comments,
        )
    except HackerNewsError as exc:
        ctx.errors.append(str(exc))
        return _finalize(ctx, started_at, [], len(queries))

    records: list[SignalRecord] = []
    for story in stories:
        try:
            record = _build_signal(ctx, story)
            records.append(record)
            debug_log(
                (
                    "[hacker-news-search-watch] + "
                    f"{story.story_id} query={story.query} score={story.score} comments={story.descendants}"
                ),
                log_file=ctx.debug_log_path,
            )
        except Exception as exc:
            ctx.errors.append(f"failed to write story {story.story_id}: {exc}")

    return _finalize(ctx, started_at, records, len(queries))


def _finalize(ctx: RunContext, started_at: str, records: list[SignalRecord], queries_checked: int) -> RunResult:
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    signal_types_count: dict[str, int] = {}
    for record in records:
        signal_types_count[record.signal_type] = signal_types_count.get(record.signal_type, 0) + 1

    status = RunStatus.SUCCESS if records else RunStatus.EMPTY
    if ctx.errors:
        status = RunStatus.FAILED

    result = RunResult(
        lane="hacker-news-search-watch",
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
    debug_log(
        f"[hacker-news-search-watch] END signals={len(records)} queries={queries_checked}",
        log_file=ctx.debug_log_path,
    )
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


register_lane("hacker-news-search-watch", collect_hacker_news_search_watch)
