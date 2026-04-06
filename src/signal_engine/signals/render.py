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
    """Render index.md from a RunResult + its signal records.

    Args:
        result: The RunResult to render.
        index_path: Path to the index.md being written. Used to compute
            relative links to signal files. If None, absolute paths are used.
    """
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
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
            title = getattr(r, "title", "") or ""
            fetched = getattr(r, "fetched_at", "") or ""
            url = getattr(r, "source_url", "") or "#"

            # Use relative path from index.md location to signal file for portability
            if index_path is not None:
                link = _signal_relative_path(index_path, r.file_path or "")
            else:
                link = r.file_path or "#"

            lines.append(
                f"| {r.signal_type} | {title} | {fetched} | @{author} | "
                f"[signal]({link}) | [source]({url}) |"
            )

    return "\n".join(lines)
