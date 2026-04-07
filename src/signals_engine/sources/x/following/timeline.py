"""X following timeline source (x-following lane).

Single stable entry point: fetch_following_timeline().
Fetches tweets from the accounts you follow (pure following stream).
"""

from pathlib import Path

from ..auth import XAuth, load_auth
from ..client import XClient
from ..errors import (
    AuthError,
    RateLimitError,
    SchemaError,
    SourceUnavailableError,
    TransportError,
)
from ..models import NormalizedTweet
from ..parser import parse_timeline_response

# X GraphQL queryId for the following/latest timeline
# Source: xfetch src/lib/query-ids/index.ts
HOME_LATEST_TIMELINE_QUERY_ID = "BKB7oi212Fi7kQtCBGE4zA"
HOME_LATEST_TIMELINE_OPERATION = "HomeLatestTimeline"

# Maximum pages to fetch (X returns ~40 tweets per page)
_MAX_PAGES = 5
# Tweets fetched per page (over-fetch to account for promoted content filtering)
_PAGE_SIZE = 40


def fetch_following_timeline(
    limit: int = 200,
    cookie_file: str | None = None,
    timeout: int = 30,
) -> list[NormalizedTweet]:
    """Fetch the X following timeline (people you follow) using native HTTP.

    This is the only function the x-following lane should call.
    All auth, HTTP, and parsing logic is encapsulated within this function.

    Unlike HomeTimeline, this endpoint returns a purer chronological stream
    of tweets from accounts you follow, without recommended content.

    Args:
        limit: Maximum number of tweets to return (default 200).
               May return slightly more due to over-fetching and dedup.
        cookie_file: Path to X.com cookie file. If None, uses default
                     ~/.signal-engine/x-cookies.json.
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
    prev_cursor: str | None = None

    remaining = limit
    pages_fetched = 0

    while remaining > 0 and pages_fetched < _MAX_PAGES:
        fetch_count = min(_PAGE_SIZE, remaining + 5)
        pages_fetched += 1

        raw = client.fetch_timeline_raw(
            query_id=HOME_LATEST_TIMELINE_QUERY_ID,
            operation_name=HOME_LATEST_TIMELINE_OPERATION,
            count=fetch_count,
            cursor=cursor,
            extra_variables=None,  # HomeLatestTimeline doesn't use extra variables
        )

        tweets = parse_timeline_response(raw, seen=seen_ids)
        all_tweets.extend(tweets)
        remaining -= len(tweets)

        cursor = _extract_cursor(raw)
        if not cursor or cursor == prev_cursor:
            break
        prev_cursor = cursor

    return all_tweets[:limit]


def _load_default_auth() -> XAuth:
    """Load auth from the default cookie file location.

    Raises:
        AuthError: if no cookie file found
    """
    default_path = Path.home() / ".signal-engine" / "x-cookies.json"
    return load_auth(str(default_path))


def _extract_cursor(raw: dict) -> str | None:
    """Extract the bottom cursor from a raw timeline response.

    HomeLatestTimeline uses the same response structure as HomeTimeline,
    so the same extraction logic applies.
    """
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
