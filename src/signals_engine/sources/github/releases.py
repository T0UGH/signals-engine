"""GitHub releases collector via gh api."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class Release:
    """A single GitHub release."""
    tag: str
    name: str
    body: str
    html_url: str
    published_at: str
    prerelease: bool
    assets: list[dict]


class GhError(Exception):
    """gh CLI execution failed."""
    pass


def _run_gh(args: list[str]) -> str:
    """Run gh CLI and return stdout. Raises GhError on non-zero exit."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as e:
        raise GhError("gh CLI not found. Is GitHub CLI installed?") from e
    except subprocess.TimeoutExpired as e:
        raise GhError(f"gh timed out after 60s: {args}") from e

    if result.returncode != 0:
        raise GhError(f"gh {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}")

    return result.stdout


def fetch_releases(
    owner: str,
    repo: str,
    lookback_days: int = 7,
    max_per_repo: int = 3,
) -> list[Release]:
    """Fetch recent releases for a GitHub repository via gh api.

    Args:
        owner: repo owner (e.g. "anthropics")
        repo: repo name (e.g. "claude-code")
        lookback_days: only include releases published within this window (default 7)
        max_per_repo: maximum number of releases to return (default 3)

    Returns:
        List of Release objects, newest first, capped to max_per_repo.
        Returns [] if no releases found or API call fails.

    Raises:
        GhError: if gh CLI is unavailable or fails (logged as warning by caller)
    """
    # Compute cutoff date
    cutoff = datetime.now(timezone.utc).replace(microsecond=0)
    from datetime import timedelta
    cutoff -= timedelta(days=lookback_days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        raw = _run_gh([
            "api",
            f"repos/{owner}/{repo}/releases",
            "--paginate",
            "--jq",
            ".[] | select(.published_at >= \"" + cutoff_str + "\")",
        ])
    except GhError:
        # No releases in window or API failure — caller handles as warning
        return []

    if not raw.strip():
        return []

    releases: list[Release] = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        try:
            obj: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue

        tag = str(obj.get("tag_name", ""))
        if not tag:
            continue

        name = str(obj.get("name") or obj.get("tag_name", ""))
        body = str(obj.get("body") or "")
        html_url = str(obj.get("html_url", ""))
        published_at = str(obj.get("published_at", ""))
        prerelease = bool(obj.get("prerelease", False))

        assets: list[dict] = []
        for asset in obj.get("assets", []) or []:
            assets.append({
                "name": str(asset.get("name", "")),
                "size_mb": round(int(asset.get("size", 0)) / (1024 * 1024), 1),
                "browser_download_url": str(asset.get("browser_download_url", "")),
            })

        releases.append(Release(
            tag=tag,
            name=name,
            body=body,
            html_url=html_url,
            published_at=published_at,
            prerelease=prerelease,
            assets=assets,
        ))

        if len(releases) >= max_per_repo:
            break

    return releases
