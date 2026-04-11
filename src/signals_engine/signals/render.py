"""Signal and index markdown rendering."""
from datetime import datetime, timezone
from pathlib import Path
from ..core import SignalRecord, RunResult
from .frontmatter import build_frontmatter


def render_signal_markdown(record: SignalRecord) -> str:
    """Render a SignalRecord to a complete markdown string (frontmatter + body)."""
    fm = build_frontmatter(record)
    body = _render_body(record)
    return f"---\n{fm}\n---\n\n{body}"


def _render_body(record: SignalRecord) -> str:
    """Render the body section of a signal. Lane-specific logic here."""
    if record.lane == "x-feed":
        return _render_x_feed_body(record)
    if record.lane == "x-following":
        return _render_x_following_body(record)
    if _is_github_repo_watch_record(record):
        return _render_github_watch_body(record)
    # Generic fallback
    lines = []
    if record.text_preview:
        lines.append(f"## Preview\n\n{record.text_preview}\n")
    if record.handle:
        lines.append(f"**Author:** @{record.handle}")
    return "\n".join(lines) if lines else ""


def _render_x_feed_body(record: SignalRecord) -> str:
    """Render x-feed specific body. Matches old shell format for Phase-1 compatibility."""
    text = record.text_preview if record.text_preview else "(no text)"
    return (
        "## Post\n\n"
        f"{text}\n\n"
        "## Engagement\n\n"
        f"- Likes: {record.likes}\n"
        f"- Retweets: {record.retweets}\n"
        f"- Replies: {record.replies}\n"
        f"- Views: {record.views}\n\n"
        "## Feed Context\n\n"
        f"- Position in session: #{record.position}\n"
        "- Feed context: not available (Phase 1)\n"
    )


def _render_x_following_body(record: SignalRecord) -> str:
    """Render x-following specific body. Matches old shell format for Phase-1 compatibility."""
    text = record.text_preview if record.text_preview else "(no text)"
    group_label = getattr(record, "group", "") or "uncategorized"
    tags = getattr(record, "tags", []) or []
    tags_str = ", ".join(tags) if tags else ""
    return (
        "## Post\n\n"
        f"{text}\n\n"
        "## Engagement\n\n"
        f"- Likes: {record.likes}\n"
        f"- Retweets: {record.retweets}\n"
        f"- Replies: {record.replies}\n"
        f"- Views: {record.views}\n\n"
        "## Enrichment\n\n"
        f"- Group: {group_label}\n"
        f"- Tags: {tags_str}\n"
    )


def _is_github_repo_watch_record(record: SignalRecord) -> bool:
    """Return True when a record belongs to the GitHub repo-watch family."""
    return record.source == "github" and record.signal_type in {"release", "changelog", "readme"}


def _render_github_watch_body(record: SignalRecord) -> str:
    """Render github-watch specific body: release notes, changelog diff, or readme diff."""
    if record.signal_type == "release":
        body_text = getattr(record, "release_body", "") or "(no release notes)"
        assets = getattr(record, "release_assets", []) or []
        parts = ["## Release Notes\n\n", f"{body_text}\n"]
        if assets:
            parts.append("## Assets\n\n")
            for a in assets:
                name = a.get("name") or a.get("Name", "asset")
                url = a.get("browser_download_url", "")
                sz = a.get("size_mb", 0)
                parts.append(f"- [{name}]({url})  ({sz} MB)\n")
        return "".join(parts)

    elif record.signal_type in ("changelog", "readme"):
        stats = getattr(record, "diff_stats", "") or ""
        diff_text = getattr(record, "diff_text", "") or "(no diff available)"
        return (
            "## Change Summary\n\n"
            f"{stats}\n\n"
            "## Diff\n\n"
            "```diff\n"
            f"{diff_text}\n"
            "```\n"
        )

    return "(unknown github-watch signal type)"


def _signal_relative_path(index_path: Path, signal_file_path: str) -> str:
    """Compute relative path from index.md to a signal file for portable links."""
    if not signal_file_path:
        return "#"
    try:
        signal_path = Path(signal_file_path).resolve()
        index_dir = index_path.parent.resolve()
        rel = signal_path.relative_to(index_dir)
        return str(rel)
    except ValueError:
        # Cross-drive or unresolved: fall back to just the filename
        return Path(signal_file_path).name


def render_index_markdown(
    result: RunResult,
    index_path: Path | None = None,
) -> str:
    """Render index.md from a RunResult + its signal records."""
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "+0000")
    session_id = result.session_id or "unknown"

    lines = [
        "---",
        f"lane: {result.lane}",
        f'date: "{result.date}"',
        f'session_id: "{session_id}"',
        f'generated_at: "{generated_at}"',
        f'status: {result.status.value}',
        "---",
        "",
        f"# {result.lane} — {result.date}",
        "",
        "## Run Summary",
        "",
        f"- Session: {session_id}",
        f"- Signals written: {result.signals_written}",
        "",
        "## Signals",
        "",
    ]

    if not result.signal_records:
        lines.append("_No signals captured._")
    else:
        lines.append(
            "| type | title | fetched_at | author | signal_link | source_url |"
        )
        lines.append("|------|-------|------------|--------|-------------|------------|")
        for r in result.signal_records:
            author = getattr(r, "handle", "") or ""
            title = (getattr(r, "title", "") or "").replace("|", "\\|")
            fetched = getattr(r, "fetched_at", "") or ""
            url = getattr(r, "source_url", "") or "#"
            if index_path is not None:
                link = _signal_relative_path(index_path, r.file_path or "")
            else:
                link = r.file_path or "#"
            lines.append(
                f"| {r.signal_type} | {title} | {fetched} | @{author} | "
                f"[signal]({link}) | [source]({url}) |"
            )

    return "\n".join(lines)
