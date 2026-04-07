"""GitHub data sources.

Public exports:
    fetch_releases: fetch GitHub releases for a repo
    fetch_content: fetch a repo file (README, CHANGELOG, etc.) by path
    diff_content: compare current content against stored state
"""

from .releases import fetch_releases
from .content import fetch_content, diff_content, compute_diff_stats

__all__ = [
    "fetch_releases",
    "fetch_content",
    "diff_content",
    "compute_diff_stats",
]
