"""x-following lane collector.

Collects posts from the X accounts you follow (pure following timeline),
with optional enrichment: handle -> group/tags metadata from config.
"""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from ..core import RunResult, RunContext, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..sources.x.following.timeline import fetch_following_timeline
from ..sources.x.errors import XSourceError
from ..signals.writer import write_signal
from ..signals.index import write_index
from ..runtime.run_manifest import write_run_manifest
from .registry import register_lane


def _make_session_id(date: str) -> str:
    """Generate a session ID: following-{date}-{short_hash}."""
    hash_input = f"following-{date}-{datetime.now().isoformat()}".encode()
    short_hash = hashlib.md5(hash_input).hexdigest()[:6]
    return f"following-{date}-{short_hash}"


def _sanitize_handle(handle: str) -> str:
    """Sanitize Twitter handle for use in filename."""
    return handle.replace("/", "_").replace("\\", "_").replace(":", "_")


def _build_enrichment_lookup(enrichment_list: list[dict]) -> dict[str, dict]:
    """Build a lowercase handle -> {group, tags} lookup dict from enrichment config.

    Args:
        enrichment_list: list of dicts with keys: handle, group, tags

    Returns:
        lowercase handle string -> {group, tags} dict
    """
    lookup: dict[str, dict] = {}
    for entry in enrichment_list:
        key = str(entry.get("handle", "")).lower()
        if key:
            lookup[key] = {
                "group": str(entry.get("group", "uncategorized")),
                "tags": list(entry.get("tags", [])),
            }
    return lookup


def _enrich_signal(handle: str, lookup: dict[str, dict]) -> tuple[str, list[str]]:
    """Look up enrichment metadata for a handle.

    Returns (group, tags). Defaults to ("uncategorized", []) if not found.
    """
    key = handle.lower()
    entry = lookup.get(key)
    if entry:
        return entry["group"], entry["tags"]
    return "uncategorized", []


def collect_x_following(ctx: RunContext) -> RunResult:
    """Collect x-following signals via native X source (no opencli, no xfetch).

    Reads source config:
        lanes["x-following"]["source"]["auth"]["cookie_file"]  (default: ~/.signal-engine/x-cookies.json)
        lanes["x-following"]["source"]["limit"]                (default: 200)
        lanes["x-following"]["source"]["timeout_seconds"]      (default: 30)
        lanes["x-following"]["enrichment"]                     (list of {handle, group, tags})

    Run status semantics:
        - source fetch fails or returns empty -> EMPTY
        - source returned data but ALL signal writes fail -> FAILED
        - source returned data + partial write failures -> FAILED
        - source returned data + all critical writes succeed -> SUCCESS
        - index.md write fails -> FAILED
        - run.json write fails -> FAILED
    """
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    warnings: list[str] = []
    errors: list[str] = []

    # Read config
    lane_config = ctx.config.get("lanes", {}).get("x-following", {})
    source_cfg = lane_config.get("source", {})
    cookie_file = source_cfg.get("auth", {}).get("cookie_file")
    limit = int(source_cfg.get("limit", 200))
    timeout = int(source_cfg.get("timeout_seconds", 30))
    enrichment_list: list[dict] = list(lane_config.get("enrichment", []))
    enrichment_lookup = _build_enrichment_lookup(enrichment_list)

    session_id = _make_session_id(ctx.date)

    ctx.ensure_dirs()

    # Fetch following timeline via native source
    tweets: list[dict] = []
    debug_log(
        f"[x-following] FETCH START cookie={cookie_file} limit={limit} timeout={timeout}",
        log_file=ctx.debug_log_path,
    )
    try:
        normalized = fetch_following_timeline(
            limit=limit,
            cookie_file=cookie_file,
            timeout=timeout,
        )
        debug_log(
            f"[x-following] FETCH END got={len(normalized)} tweets",
            log_file=ctx.debug_log_path,
        )
        tweets = [
            {
                "id": t.id,
                "author": t.author,
                "text": t.text,
                "url": t.url,
                "created_at": t.created_at,
                "likes": t.likes,
                "retweets": t.retweets,
                "replies": t.replies,
                "views": t.views,
            }
            for t in normalized
        ]
    except XSourceError as e:
        debug_log(f"[x-following] FETCH ERROR: {e}", log_file=ctx.debug_log_path)
        errors.append(f"source fetch failed: {e}")

    if not tweets:
        finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
        index_path = ctx.index_path
        run_json_path = ctx.run_json_path

        result_for_write = RunResult(
            lane="x-following",
            date=ctx.date,
            status=RunStatus.EMPTY,
            started_at=started_at,
            session_id=session_id,
            finished_at=finished_at,
            warnings=warnings,
            errors=errors,
            signal_records=[],
            repos_checked=1,
            signals_written=0,
            signal_types_count={},
            index_file=str(index_path),
        )

        index_ok = _write_index_to_file(result_for_write, index_path)
        run_ok = True
        if index_ok:
            run_ok = _write_manifest_to_file(result_for_write, run_json_path)

        if not (index_ok and run_ok):
            result_for_write.status = RunStatus.FAILED

        return result_for_write

    # Map tweets to SignalRecord with enrichment
    signal_records: list[SignalRecord] = []
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    debug_log(
        f"[x-following] SIGNAL WRITE START count={len(tweets)}",
        log_file=ctx.debug_log_path,
    )
    for position, tweet in enumerate(tweets, start=1):
        post_id = str(tweet.get("id", ""))
        handle = str(tweet.get("author", ""))
        text = str(tweet.get("text", ""))
        url = str(tweet.get("url", ""))
        created_at = str(tweet.get("created_at", ""))

        # Enrichment lookup
        group, tags = _enrich_signal(handle, enrichment_lookup)

        safe_handle = _sanitize_handle(handle)
        filename = f"{safe_handle}__post__{post_id}.md"
        file_path = str(ctx.signals_dir / filename)

        record = SignalRecord(
            lane="x-following",
            signal_type="post",
            source="x",
            entity_type="author",
            entity_id=handle,
            title=f"@{handle}",
            source_url=url,
            fetched_at=fetched_at,
            file_path=file_path,
            # x-following specific
            session_id=session_id,
            handle=handle,
            post_id=post_id,
            created_at=created_at,
            position=position,
            text_preview=text[:120] if text else "",
            likes=int(tweet.get("likes") or 0),
            retweets=int(tweet.get("retweets") or 0),
            replies=int(tweet.get("replies") or 0),
            views=int(tweet.get("views") or 0),
            group=group,
            tags=tags,
        )

        try:
            write_signal(record)
            signal_records.append(record)
        except Exception as e:
            debug_log(
                f"[x-following] SIGNAL WRITE ERROR {filename}: {e}",
                log_file=ctx.debug_log_path,
            )
            errors.append(f"failed to write {filename}: {e}")

    debug_log(
        f"[x-following] SIGNAL WRITE END written={len(signal_records)}",
        log_file=ctx.debug_log_path,
    )

    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    signal_types_count: dict[str, int] = {}
    for r in signal_records:
        signal_types_count[r.signal_type] = signal_types_count.get(r.signal_type, 0) + 1

    index_path = ctx.index_path
    run_json_path = ctx.run_json_path

    result_for_write = RunResult(
        lane="x-following",
        date=ctx.date,
        status=RunStatus.SUCCESS,
        started_at=started_at,
        session_id=session_id,
        finished_at=finished_at,
        warnings=warnings,
        errors=errors,
        signal_records=signal_records,
        repos_checked=1,
        signals_written=len(signal_records),
        signal_types_count=signal_types_count,
        index_file=str(index_path),
    )

    index_ok = _write_index_to_file(result_for_write, index_path)
    debug_log(
        f"[x-following] INDEX WRITE END ok={index_ok}",
        log_file=ctx.debug_log_path,
    )

    if errors or not index_ok:
        result_for_write.status = RunStatus.FAILED

    debug_log(
        f"[x-following] RUNJSON WRITE START status={result_for_write.status.value}",
        log_file=ctx.debug_log_path,
    )
    _write_manifest_to_file(result_for_write, run_json_path)
    debug_log(f"[x-following] RUNJSON WRITE END", log_file=ctx.debug_log_path)

    return result_for_write


def _write_index_to_file(result: RunResult, index_path: Path) -> bool:
    """Write index.md from a real RunResult. Returns True on success."""
    try:
        write_index(result, index_path)
        return True
    except Exception as e:
        result.errors.append(f"failed to write index.md: {e}")
        return False


def _write_manifest_to_file(result: RunResult, run_json_path: Path) -> bool:
    """Write run.json from a real RunResult. Returns True on success."""
    try:
        write_run_manifest(result, run_json_path)
        return True
    except Exception as e:
        result.errors.append(f"failed to write run.json: {e}")
        return False


register_lane("x-following", collect_x_following)
