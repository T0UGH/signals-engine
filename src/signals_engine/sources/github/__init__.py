"""GitHub data sources.

Public exports:
    fetch_releases: fetch GitHub releases for a repo
    fetch_merged_prs: fetch recently merged PRs for a repo
    fetch_recent_commits: fetch recent commits for a repo
    fetch_content: fetch a repo file (README, CHANGELOG, etc.) by path
    diff_content: compare current content against stored state
"""

from .releases import fetch_releases
from .prs import fetch_merged_prs
from .commits import fetch_recent_commits
from .content import fetch_content, diff_content, compute_diff_stats

__all__ = [
    "fetch_releases",
    "fetch_merged_prs",
    "fetch_recent_commits",
    "fetch_content",
    "diff_content",
    "compute_diff_stats",
]
