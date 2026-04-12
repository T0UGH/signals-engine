"""X following timeline source (x-following lane)."""

from ..auth import default_cookie_file_path, load_auth, resolve_auth_config
from ..browser_session import XBrowserSessionClient
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
    auth_config: dict | None = None,
) -> list[NormalizedTweet]:
    """Fetch the X following timeline (people you follow).

    This is the only function the x-following lane should call.
    It dispatches to browser-session auth by default, preferring an attached
    logged-in host browser session, and keeps cookie-file auth as an explicit
    legacy fallback.

    Unlike HomeTimeline, this endpoint returns a purer chronological stream
    of tweets from accounts you follow, without recommended content.

    Args:
        limit: Maximum number of tweets to return (default 200).
               May return slightly more due to over-fetching and dedup.
        cookie_file: Legacy compatibility override for cookie-file mode.
        timeout: Request timeout in seconds (default 30).
        auth_config: Lane auth config dict.

    Returns:
        List of NormalizedTweet sorted by position (newest first).

    Raises:
        AuthError: cookie missing/invalid
        TransportError: network failure
        RateLimitError: HTTP 429
        SchemaError: X API response structure changed
        SourceUnavailableError: X server error (5xx)
    """
    client = _make_timeline_client(
        auth_config=auth_config,
        cookie_file=cookie_file,
        timeout=timeout,
    )

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


def _make_timeline_client(
    *,
    auth_config: dict | None,
    cookie_file: str | None,
    timeout: int,
):
    resolved_auth = resolve_auth_config(auth_config, cookie_file=cookie_file)
    if resolved_auth.mode == "browser-session":
        return XBrowserSessionClient(resolved_auth, timeout=timeout)

    auth = load_auth(resolved_auth.cookie_file) if resolved_auth.cookie_file else _load_default_auth()
    return XClient(auth, timeout=timeout)


def _load_default_auth():
    """Load legacy auth from the default cookie file location."""
    return load_auth(str(default_cookie_file_path()))


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
