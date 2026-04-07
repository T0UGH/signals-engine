"""GitHub file content fetch and diff.

Used for changelog and README state tracking.
"""
from __future__ import annotations

import base64
import subprocess
import difflib
from dataclasses import dataclass

from .releases import GhError


def _run_gh(args: list[str]) -> str:
    """Run gh CLI and return stdout. Raises GhError on non-zero exit."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as e:
        raise GhError("gh CLI not found.") from e
    except subprocess.TimeoutExpired as e:
        raise GhError(f"gh timed out after 30s: {args}") from e

    if result.returncode != 0:
        raise GhError(f"gh {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}")

    return result.stdout


@dataclass
class ContentResult:
    """Result of fetching a GitHub repo file."""
    content: str
    sha: str
    path: str


@dataclass
class DiffResult:
    """Diff between current content and previous state."""
    changed: bool
    is_first: bool  # True if no previous state existed
    diff_text: str
    stats: str  # e.g. "+10 lines, -3 lines"


def fetch_content(owner: str, repo: str, path: str) -> ContentResult | None:
    """Fetch a single file from a GitHub repo via gh api.

    Args:
        owner: repo owner
        repo: repo name
        path: file path within repo (e.g. "CHANGELOG.md")

    Returns:
        ContentResult with decoded content and sha, or None if file not found.

    Raises:
        GhError: if gh CLI fails for non-404 reasons
    """
    try:
        raw = _run_gh([
            "api",
            f"repos/{owner}/{repo}/contents/{path}",
            "--jq",
            "{content: .content, sha: .sha, path: .path}",
        ])
    except GhError as e:
        if "404" in str(e):
            return None
        raise

    import json
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None

    encoded = obj.get("content", "")
    if not encoded:
        return None

    # GitHub API returns content base64-encoded with line breaks at 80 chars
    decoded = base64.b64decode(encoded).decode("utf-8", errors="replace")

    return ContentResult(
        content=decoded,
        sha=str(obj.get("sha", "")),
        path=str(obj.get("path", path)),
    )


def compute_diff_stats(old: str, new: str) -> str:
    """Compute line-count diff stats between two content strings.

    Returns: e.g. "+10 lines, -3 lines"
    """
    diff = list(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        lineterm="",
    ))
    added = 0
    removed = 0
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return f"+{added} lines, -{removed} lines"


def diff_content(
    old_content: str | None,
    new_content: str,
) -> DiffResult:
    """Compare new content against stored state.

    Args:
        old_content: previous content (None if first run)
        new_content: current content

    Returns:
        DiffResult with changed flag, diff text, and stats.

    Raises:
        ValueError: if new_content is empty/None
    """
    if not new_content:
        raise ValueError("new_content must be non-empty")

    if old_content is None:
        return DiffResult(
            changed=False,
            is_first=True,
            diff_text="",
            stats="",
        )

    if old_content == new_content:
        return DiffResult(
            changed=False,
            is_first=False,
            diff_text="",
            stats="",
        )

    # Content differs
    diff_lines = list(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        lineterm="",
    ))
    # Skip the --- / +++ header lines
    diff_text = "".join(diff_lines[3:] if len(diff_lines) > 2 else diff_lines)
    stats = compute_diff_stats(old_content, new_content)

    return DiffResult(
        changed=True,
        is_first=False,
        diff_text=diff_text,
        stats=stats,
    )
