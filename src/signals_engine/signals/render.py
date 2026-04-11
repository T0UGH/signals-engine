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
    if record.lane == "reddit-watch":
        return _render_reddit_watch_body(record)
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


def _render_reddit_watch_body(record: SignalRecord) -> str:
    """Render reddit-watch specific body."""
    text = record.text_preview if record.text_preview else "(no body text)"
    subreddit = getattr(record, "group", "") or "reddit"
    top_comments_text = getattr(record, "top_comments_text", "") or ""
    query = getattr(record, "query", "") or ""
    lines = [
        "## Post\n\n",
        f"{text}\n\n",
        "## Thread Context\n\n",
        f"- Community: {subreddit}\n",
        f"- Score: {record.likes}\n",
        f"- Comments: {record.replies}\n",
    ]
    if query:
        lines.append(f"- Matched query: {query}\n")
    if record.handle:
        lines.append(f"- Author: @{record.handle}\n")
    if top_comments_text:
        lines.extend(["\n## Top Comments\n\n", f"{top_comments_text}\n"])
    return "".join(lines)


def _is_github_repo_watch_record(record: SignalRecord) -> bool:
    """Return True when a record belongs to the GitHub repo-watch family."""
    return record.source == "github" and record.signal_type in {"release", "changelog", "readme", "merged_pr", "commit"}


def _render_github_watch_body(record: SignalRecord) -> str:
    """Render GitHub repo-watch signals."""
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

    if record.signal_type in ("changelog", "readme"):
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

    if record.signal_type == "merged_pr":
        pr_number = getattr(record, "pr_number", 0) or getattr(record, "post_id", "")
        summary = getattr(record, "text_preview", "") or "(no PR summary)"
        author = getattr(record, "handle", "") or "unknown"
        merged_at = getattr(record, "created_at", "") or ""
        merge_commit_sha = getattr(record, "merge_commit_sha", "") or ""
        lines = [
            f"## Merged PR #{pr_number}\n\n",
            f"**Title:** {record.title}\n\n",
            f"**Author:** @{author}\n",
        ]
        if merged_at:
            lines.append(f"**Merged at:** {merged_at}\n")
        if merge_commit_sha:
            lines.append(f"**Merge commit:** `{merge_commit_sha[:7]}`\n")
        lines.append("\n## Summary\n\n")
        lines.append(f"{summary}\n")
        return "".join(lines)

    if record.signal_type == "commit":
        commit_sha = getattr(record, "commit_sha", "") or getattr(record, "post_id", "")
        author = getattr(record, "handle", "") or "unknown"
        committed_at = getattr(record, "created_at", "") or ""
        summary = getattr(record, "text_preview", "") or record.title or "(no commit message)"
        lines = [
            f"## Commit {commit_sha[:7]}\n\n",
            f"**Author:** @{author}\n",
        ]
        if committed_at:
            lines.append(f"**Committed at:** {committed_at}\n")
        lines.append("\n## Message\n\n")
        lines.append(f"{summary}\n")
        return "".join(lines)

    return "(unknown github repo-watch signal type)"


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
