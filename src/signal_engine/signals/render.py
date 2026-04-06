"""Signal and index markdown rendering."""
from datetime import datetime, timezone
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
    # Generic fallback
    lines = []
    if record.text_preview:
        lines.append(f"## Preview\n\n{record.text_preview}\n")
    if record.handle:
        lines.append(f"**Author:** @{record.handle}")
    return "\n".join(lines) if lines else ""


def _render_x_feed_body(record: SignalRecord) -> str:
    """Render x-feed specific body. Matches old shell format for Phase-1 compatibility."""
    # Note: text_preview already truncated to 120 chars in x_feed.py
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


def render_index_markdown(result: RunResult) -> str:
    """Render index.md from a RunResult + its signal records."""
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    session_id = f"se-{result.date}-{int(datetime.now().timestamp())}"

    lines = [
        "---",
        f"lane: {result.lane}",
        f'date: "{result.date}"',
        f'session_id: "{session_id}"',
        f'generated_at: "{fetched_at}"',
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
            title = getattr(r, "title", "") or ""
            fetched = getattr(r, "fetched_at", "") or ""
            url = getattr(r, "source_url", "") or "#"
            link = r.file_path or "#"
            lines.append(
                f"| {r.signal_type} | {title} | {fetched} | @{author} | "
                f"[signal]({link}) | [source]({url}) |"
            )

    return "\n".join(lines)
