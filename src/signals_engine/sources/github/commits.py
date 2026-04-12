"""GitHub commits collector via gh api."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .releases import GhError


@dataclass
class RepoCommit:
    """A recent repository commit."""
    sha: str
    message: str
    html_url: str
    committed_at: str
    author: str


def _run_gh(args: list[str]) -> str:
    """Run gh CLI and return stdout. Raises GhError on non-zero exit."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise GhError("gh CLI not found. Is GitHub CLI installed?") from exc
    except subprocess.TimeoutExpired as exc:
        raise GhError(f"gh timed out after 60s: {args}") from exc

    if result.returncode != 0:
        raise GhError(f"gh {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}")

    return result.stdout


def fetch_recent_commits(
    owner: str,
    repo: str,
    lookback_days: int = 7,
    max_per_repo: int = 10,
) -> list[RepoCommit]:
    """Fetch recent commits for a GitHub repository via gh api."""
    cutoff = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=lookback_days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        raw = _run_gh([
            "api",
            f"repos/{owner}/{repo}/commits?per_page=100",
            "--jq",
            ".[] | select(.commit.committer.date >= \"" + cutoff_str + "\")",
        ])
    except GhError:
        return []

    if not raw.strip():
        return []

    commits: list[RepoCommit] = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        sha = str(obj.get("sha") or "")
        commit = obj.get("commit") or {}
        committed_at = str(((commit.get("committer") or {}).get("date")) or "")
        message = str(commit.get("message") or "")
        if not sha or not committed_at:
            continue

        author = ""
        author_obj = obj.get("author") or {}
        if isinstance(author_obj, dict):
            author = str(author_obj.get("login") or "")
        if not author:
            author = str(((commit.get("author") or {}).get("name")) or "")

        commits.append(RepoCommit(
            sha=sha,
            message=message,
            html_url=str(obj.get("html_url") or ""),
            committed_at=committed_at,
            author=author,
        ))
        if len(commits) >= max_per_repo:
            break

    return commits
