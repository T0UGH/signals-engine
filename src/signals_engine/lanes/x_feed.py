"""x-feed lane collector."""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from ..core import RunResult, RunContext, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..sources.x.feed.timeline import fetch_home_timeline
from ..sources.x.errors import XSourceError
from ..signals.writer import write_signal
from ..signals.index import write_index
from ..runtime.run_manifest import write_run_manifest
from .registry import register_lane


def _make_session_id(date: str) -> str:
    """Generate a session ID compatible with old shell format: feed-{date}-{short_hash}."""
    hash_input = f"feed-{date}-{datetime.now().isoformat()}".encode()
    short_hash = hashlib.md5(hash_input).hexdigest()[:6]
    return f"feed-{date}-{short_hash}"


def _sanitize_handle(handle: str) -> str:
    """Sanitize Twitter handle for use in filename."""
    return handle.replace("/", "_").replace("\\", "_").replace(":", "_")


def collect_x_feed(ctx: RunContext) -> RunResult:
    """Collect x-feed signals via native X source (no opencli).

    Reads source config:
        lanes["x-feed"]["source"]["auth"]["mode"]           (default: browser-session)
        lanes["x-feed"]["source"]["auth"]["cdp_url"]        (default: http://127.0.0.1:9222)
        lanes["x-feed"]["source"]["auth"]["cookie_file"]    (legacy fallback)
        lanes["x-feed"]["source"]["limit"]                  (default: 100)
        lanes["x-feed"]["source"]["timeout_seconds"]        (default: 30)

    Run status semantics:
        - source fetch fails or returns empty -> EMPTY
        - source returned data but ALL signal writes fail -> FAILED
        - source returned data + partial write failures -> FAILED
        - source returned data + all critical writes succeed -> SUCCESS
        - index.md write fails -> FAILED
        - run.json write fails -> FAILED
    """
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "+0000")
    warnings: list[str] = []
    errors: list[str] = []

    # Read config
    lane_config = ctx.config.get("lanes", {}).get("x-feed", {})
    source_cfg = lane_config.get("source", {})
    auth_config = dict(source_cfg.get("auth", {}))
    auth_mode = str(
        auth_config.get("mode")
        or ("cookie-file" if auth_config.get("cookie_file") else "browser-session")
    )
    limit = int(source_cfg.get("limit", 100))
    timeout = int(source_cfg.get("timeout_seconds", 30))

    session_id = _make_session_id(ctx.date)

    ctx.ensure_dirs()

    # Fetch feed via native source
    tweets: list[dict] = []
    debug_log(
        f"[x-feed] FETCH START auth_mode={auth_mode} limit={limit} timeout={timeout}",
        log_file=ctx.debug_log_path,
    )
    try:
        normalized = fetch_home_timeline(
            limit=limit,
            timeout=timeout,
            auth_config=auth_config,
        )
        debug_log(f"[x-feed] FETCH END got={len(normalized)} tweets", log_file=ctx.debug_log_path)
        # NormalizedTweet -> plain dict for signal mapping
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
        debug_log(f"[x-feed] FETCH ERROR: {e}", log_file=ctx.debug_log_path)
        errors.append(f"source fetch failed: {e}")

    if not tweets:
        finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "+0000")
        index_path = ctx.index_path
        run_json_path = ctx.run_json_path

        # Build real RunResult with provisional EMPTY status
        result_for_write = RunResult(
            lane="x-feed",
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

        # Write artifacts, then downgrade status if writes failed
        index_ok = _write_index_to_file(result_for_write, index_path)
        run_ok = True
        if index_ok:
            run_ok = _write_manifest_to_file(result_for_write, run_json_path)

        write_ok = index_ok and run_ok
        if not write_ok:
            result_for_write.status = RunStatus.FAILED

        return result_for_write

    # Map tweets to SignalRecord
    signal_records: list[SignalRecord] = []
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    debug_log(f"[x-feed] SIGNAL WRITE START count={len(tweets)}", log_file=ctx.debug_log_path)
    for position, tweet in enumerate(tweets, start=1):
        post_id = str(tweet.get("id", ""))
        handle = str(tweet.get("author", ""))
        text = str(tweet.get("text", ""))
        url = str(tweet.get("url", ""))
        created_at = str(tweet.get("created_at", ""))

        safe_handle = _sanitize_handle(handle)
        filename = f"{safe_handle}__feed__{post_id}.md"
        file_path = str(ctx.signals_dir / filename)

        record = SignalRecord(
            lane="x-feed",
            signal_type="feed-exposure",
            source="x",
            entity_type="author",
            entity_id=handle,
            title=f"@{handle} #{position}",
            source_url=url,
            fetched_at=fetched_at,
            file_path=file_path,
            # x-feed specific
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
        )

        try:
            write_signal(record)
            signal_records.append(record)
        except Exception as e:
            debug_log(f"[x-feed] SIGNAL WRITE ERROR {filename}: {e}", log_file=ctx.debug_log_path)
            errors.append(f"failed to write {filename}: {e}")
    debug_log(f"[x-feed] SIGNAL WRITE END written={len(signal_records)}", log_file=ctx.debug_log_path)

    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "+0000")
    signal_types_count: dict[str, int] = {}
    for r in signal_records:
        signal_types_count[r.signal_type] = signal_types_count.get(r.signal_type, 0) + 1

    index_path = ctx.index_path
    run_json_path = ctx.run_json_path

    # Build real RunResult with provisional SUCCESS status
    result_for_write = RunResult(
        lane="x-feed",
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

    # Write index.md first, then determine final status, then write run.json last
    debug_log(f"[x-feed] INDEX WRITE START path={index_path}", log_file=ctx.debug_log_path)
    index_ok = _write_index_to_file(result_for_write, index_path)
    debug_log(f"[x-feed] INDEX WRITE END ok={index_ok}", log_file=ctx.debug_log_path)

    signal_failure = bool(errors)
    if signal_failure or not index_ok:
        result_for_write.status = RunStatus.FAILED
        # Preserve any errors accumulated in result.errors (e.g. from _write_index_to_file)
        result_for_write.errors = list(result_for_write.errors)

    # run.json is written AFTER final status is determined, so it always reflects the true final state
    debug_log(f"[x-feed] RUNJSON WRITE START path={run_json_path} status={result_for_write.status.value}", log_file=ctx.debug_log_path)
    _write_manifest_to_file(result_for_write, run_json_path)
    debug_log(f"[x-feed] RUNJSON WRITE END", log_file=ctx.debug_log_path)

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


register_lane("x-feed", collect_x_feed)
