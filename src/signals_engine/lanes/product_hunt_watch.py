"""product-hunt-watch lane collector.

Collects featured Product Hunt products matching configured topics.
Authentication can come from `api.token` directly or from the environment
variable named by `api.token_env` (default: `PH_API_TOKEN`). If neither is
available, the lane skips gracefully.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

from ..core import RunResult, RunContext, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..sources.producthunt import fetch_posts, match_posts_by_topics, PHError
from ..signals.writer import write_signal
from ..signals.index import write_index
from ..runtime.run_manifest import write_run_manifest
from .registry import register_lane


def _escape_yaml(text: str) -> str:
    """Escape a string for use in YAML double-quoted value."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "").strip()


def _build_signal(
    ctx: RunContext,
    product_slug: str,
    product_name: str,
    tagline: str,
    description: str,
    votes_count: int,
    comments_count: int,
    featured_at: str,
    website: str,
    ph_url: str,
    topic_slug: str,
    topic_name: str,
    makers: list[tuple[str, str]],
) -> SignalRecord:
    """Build and write one product-hunt signal."""
    filename = f"{product_slug}__{topic_slug}__producthunt_topic_hit__{ctx.date}.md"
    file_path = str(ctx.signals_dir / filename)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    # Build body
    tagline_text = tagline if tagline else "(no tagline)"
    desc_text = description if description and description != "null" else ""
    makers_text = "\n".join(
        f"- {name} (@{username})" for name, username in makers
    ) if makers else "- (no makers listed)"

    body_parts = [
        f"## {product_name}\n",
        f"\n> {tagline_text}\n",
    ]
    if desc_text:
        body_parts.extend([f"\n{desc_text}\n"])

    body_parts.extend([
        "\n## Snapshot\n",
        f"- **Votes**: {votes_count:,}\n",
        f"- **Comments**: {comments_count:,}\n",
        f"- **Featured**: {featured_at}\n",
        f"- **Topic**: {topic_name}\n\n",
        "## Links\n",
        f"- Product Hunt: {ph_url}\n",
    ])
    if website and website != "null":
        body_parts.append(f"- Website: {website}\n")

    body_parts.extend([
        "\n## Makers\n\n",
        f"{makers_text}\n",
    ])

    record = SignalRecord(
        lane="product-hunt-watch",
        signal_type="producthunt_topic_hit",
        source="producthunt",
        entity_type="product",
        entity_id=product_slug,
        title=f"{product_name} — {tagline_text[:50]}",
        source_url=ph_url,
        fetched_at=fetched_at,
        file_path=file_path,
        # product-hunt specific
        session_id="",
        handle=product_name,
        post_id=topic_slug,
        created_at=featured_at,
        # repurposed fields for product-hunt data
        likes=votes_count,
        group=topic_name,
        text_preview=tagline_text[:120],
    )
    write_signal(record)
    return record


def collect_product_hunt_watch(ctx: RunContext) -> RunResult:
    """Collect product-hunt-watch signals.

    Config keys read:
        lanes["product-hunt-watch"]["api"]["token"]       (optional; direct token, highest priority)
        lanes["product-hunt-watch"]["api"]["token_env"]   (default: PH_API_TOKEN)
        lanes["product-hunt-watch"]["api"]["lookback_days"] (default: 1)
        lanes["product-hunt-watch"]["api"]["max_pages"]    (default: 3)
        lanes["product-hunt-watch"]["api"]["max_per_topic"] (default: 20)
        lanes["product-hunt-watch"]["topics"]            (list of topic names)

    Token lookup order is: `api.token`, then `os.environ[api.token_env]`, then empty.
    If no API token is available, the lane produces EMPTY without error.
    """
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    warnings: list[str] = []
    errors: list[str] = []

    lane_config = ctx.config.get("lanes", {}).get("product-hunt-watch", {})
    api_cfg = lane_config.get("api", {})
    config_token = str(api_cfg.get("token", "") or "").strip()
    token_env = str(api_cfg.get("token_env", "PH_API_TOKEN") or "").strip()
    env_token = os.environ.get(token_env, "").strip() if token_env else ""
    token = config_token or env_token

    if not token:
        debug_log("[product-hunt-watch] PH_API_TOKEN not set, skipping", log_file=ctx.debug_log_path)
        warnings.append("PH_API_TOKEN not set — lane skipped gracefully")
        topics: list[str] = list(lane_config.get("topics", []))
        # Return EMPTY without attempting to write any signals
        finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
        result = RunResult(
            lane="product-hunt-watch",
            date=ctx.date,
            status=RunStatus.EMPTY,
            started_at=started_at,
            session_id=None,
            finished_at=finished_at,
            warnings=warnings,
            errors=[],
            signal_records=[],
            repos_checked=len(topics),
            signals_written=0,
            signal_types_count={},
            index_file=str(ctx.index_path),
        )
        _write_index_to_file(result, ctx.index_path)
        _write_manifest_to_file(result, ctx.run_json_path)
        return result

    lookback_days = int(api_cfg.get("lookback_days", 1))
    max_pages = int(api_cfg.get("max_pages", 3))
    max_per_topic = int(api_cfg.get("max_per_topic", 20))
    topics: list[str] = list(lane_config.get("topics", []))

    # Compute posted_after date
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=lookback_days)
    posted_after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    debug_log(
        f"[product-hunt-watch] START topics={topics} postedAfter={posted_after}",
        log_file=ctx.debug_log_path,
    )

    all_records: list[SignalRecord] = []
    ctx.ensure_dirs()
    topic_counts: dict[str, int] = {}

    if token:
        try:
            posts = fetch_posts(
                token=token,
                posted_after=posted_after,
                max_pages=max_pages,
                timeout=30,
            )
            debug_log(f"[product-hunt-watch] fetched {len(posts)} posts", log_file=ctx.debug_log_path)

            hits = match_posts_by_topics(posts, topics)
            debug_log(f"[product-hunt-watch] {len(hits)} topic-matched hits", log_file=ctx.debug_log_path)

            for post, topic in hits:
                topic_count = topic_counts.get(topic.slug, 0)
                if topic_count >= max_per_topic:
                    debug_log(
                        f"[product-hunt-watch]   . {post.name} ({topic.slug}): max_per_topic reached",
                        log_file=ctx.debug_log_path,
                    )
                    continue

                makers = [(m.name, m.username) for m in post.makers]
                try:
                    record = _build_signal(
                        ctx=ctx,
                        product_slug=post.slug,
                        product_name=post.name,
                        tagline=post.tagline,
                        description=post.description,
                        votes_count=post.votes_count,
                        comments_count=post.comments_count,
                        featured_at=post.featured_at,
                        website=post.website,
                        ph_url=post.url,
                        topic_slug=topic.slug,
                        topic_name=topic.name,
                        makers=makers,
                    )
                    all_records.append(record)
                    topic_counts[topic.slug] = topic_count + 1
                    debug_log(
                        f"[product-hunt-watch]   + {post.name} ({topic.slug}) votes={post.votes_count}",
                        log_file=ctx.debug_log_path,
                    )
                except Exception as e:
                    debug_log(f"[product-hunt-watch]   ERROR {post.name}: {e}", log_file=ctx.debug_log_path)
                    errors.append(f"failed to write signal {post.name}: {e}")

        except PHError as e:
            debug_log(f"[product-hunt-watch] PHError: {e}", log_file=ctx.debug_log_path)
            errors.append(f"Product Hunt API error: {e}")
    else:
        debug_log("[product-hunt-watch] skipping: no token", log_file=ctx.debug_log_path)

    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    signal_types_count: dict[str, int] = {}
    for r in all_records:
        signal_types_count[r.signal_type] = signal_types_count.get(r.signal_type, 0) + 1

    if all_records:
        status = RunStatus.SUCCESS
    elif errors:
        status = RunStatus.FAILED
    else:
        status = RunStatus.EMPTY

    index_path = ctx.index_path
    run_json_path = ctx.run_json_path

    result = RunResult(
        lane="product-hunt-watch",
        date=ctx.date,
        status=status,
        started_at=started_at,
        session_id=None,
        finished_at=finished_at,
        warnings=warnings,
        errors=errors,
        signal_records=all_records,
        repos_checked=len(topics),
        signals_written=len(all_records),
        signal_types_count=signal_types_count,
        index_file=str(index_path),
    )

    index_ok = _write_index_to_file(result, index_path)
    if errors or not index_ok:
        result.status = RunStatus.FAILED

    _write_manifest_to_file(result, run_json_path)
    debug_log(
        f"[product-hunt-watch] END signals={len(all_records)} topics_checked={len(topics)}",
        log_file=ctx.debug_log_path,
    )
    return result


def _write_index_to_file(result: RunResult, index_path: Path) -> bool:
    try:
        write_index(result, index_path)
        return True
    except Exception as e:
        result.errors.append(f"failed to write index.md: {e}")
        return False


def _write_manifest_to_file(result: RunResult, run_json_path: Path) -> bool:
    try:
        write_run_manifest(result, run_json_path)
        return True
    except Exception as e:
        result.errors.append(f"failed to write run.json: {e}")
        return False


register_lane("product-hunt-watch", collect_product_hunt_watch)
