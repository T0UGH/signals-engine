"""GitHub merged pull requests collector via gh api."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .releases import GhError


@dataclass
class MergedPullRequest:
    """A merged pull request."""
    number: int
    title: str
    body: str
    html_url: str
    merged_at: str
    author: str
    merge_commit_sha: str


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


def fetch_merged_prs(
    owner: str,
    repo: str,
    lookback_days: int = 7,
    max_per_repo: int = 10,
) -> list[MergedPullRequest]:
    """Fetch recently merged PRs for a GitHub repository via gh api."""
    cutoff = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=lookback_days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        raw = _run_gh([
            "api",
            f"repos/{owner}/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100",
            "--jq",
            ".[] | select(.merged_at != null and .merged_at >= \"" + cutoff_str + "\")",
        ])
    except GhError:
        return []

    if not raw.strip():
        return []

    prs: list[MergedPullRequest] = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        number = obj.get("number")
        merged_at = str(obj.get("merged_at") or "")
        if number is None or not merged_at:
            continue

        author = ""
        user = obj.get("user") or {}
        if isinstance(user, dict):
            author = str(user.get("login") or "")

        prs.append(MergedPullRequest(
            number=int(number),
            title=str(obj.get("title") or f"PR #{number}"),
            body=str(obj.get("body") or ""),
            html_url=str(obj.get("html_url") or ""),
            merged_at=merged_at,
            author=author,
            merge_commit_sha=str(obj.get("merge_commit_sha") or ""),
        ))
        if len(prs) >= max_per_repo:
            break

    return prs
