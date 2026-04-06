"""X home timeline entry point.

This is the single stable entry point exposed to x-feed lane code.
All internal details (auth, HTTP, parsing) are encapsulated here.
"""

import math
from pathlib import Path
from typing import Any

from .auth import XAuth, load_auth
from .client import XClient
from .errors import (
    AuthError,
    RateLimitError,
    SchemaError,
    SourceUnavailableError,
    TransportError,
    XSourceError,
)
from .models import NormalizedTweet

# Maximum pages to fetch (X returns ~40 tweets per page)
_MAX_PAGES = 5
# Tweets fetched per page (over-fetch to account for promoted content filtering)
_PAGE_SIZE = 40


def fetch_home_timeline(
    limit: int = 100,
    cookie_file: str | None = None,
    timeout: int = 30,
) -> list[NormalizedTweet]:
    """Fetch the X home timeline using native HTTP (no opencli).

    This is the only function the x-feed lane should call. All auth, HTTP,
    and parsing logic is encapsulated within this function.

    Args:
        limit: Maximum number of tweets to return (default 100).
               May return slightly more due to over-fetching and dedup.
        cookie_file: Path to X.com cookie file. If None, uses default
                     discovery order (see load_auth).
        timeout: HTTP request timeout in seconds (default 30).

    Returns:
        List of NormalizedTweet sorted by position (newest first).

    Raises:
        AuthError: cookie missing/invalid
        TransportError: network failure
        RateLimitError: HTTP 429
        SchemaError: X API response structure changed
        SourceUnavailableError: X server error (5xx)
    """
    auth = load_auth(cookie_file) if cookie_file else _load_default_auth()
    client = XClient(auth, timeout=timeout)

    all_tweets: list[NormalizedTweet] = []
    seen_ids: set[str] = set()
    cursor: str | None = None

    remaining = limit
    pages_fetched = 0

    while remaining > 0 and pages_fetched < _MAX_PAGES:
        fetch_count = min(_PAGE_SIZE, remaining + 5)  # over-fetch slightly
        pages_fetched += 1

        raw = client.fetch_timeline_raw(limit=fetch_count, cursor=cursor)

        tweets = _parse_and_dedup(raw, seen_ids)
        all_tweets.extend(tweets)
        remaining -= len(tweets)

        # Determine next cursor
        cursor = _extract_cursor(raw)
        if not cursor or cursor == (getattr(raw, "_cursor", None)):
            # No more pages
            break

    return all_tweets[:limit]


def _load_default_auth() -> XAuth:
    """Load auth from the default cookie file location.

    Raises:
        AuthError: if no cookie file found
    """
    default_path = Path.home() / ".signal-engine" / "x-cookies.json"
    return load_auth(str(default_path))


def _parse_and_dedup(raw: dict, seen: set[str]) -> list[NormalizedTweet]:
    """Parse response and deduplicate against already-seen IDs."""
    from .parser import parse_timeline_response
    return parse_timeline_response(raw)


def _extract_cursor(raw: dict) -> str | None:
    """Extract the bottom cursor from a raw timeline response."""
    try:
        instructions = (
            raw.get("data", {})
            .get("home", {})
            .get("home_timeline_urt", {})
            .get("instructions", [])
        )
    except (KeyError, TypeError):
        return None

    for inst in instructions:
        for entry in inst.get("entries", []):
            content = entry.get("content", {})
            entry_type = content.get("entryType") or content.get("__typename", "")
            if entry_type == "TimelineTimelineCursor":
                if content.get("cursorType") == "Bottom":
                    return str(content.get("value") or "")
            entry_id = str(entry.get("entryId", ""))
            if entry_id.startswith("cursor-bottom-"):
                return str(content.get("value") or "")
    return None
