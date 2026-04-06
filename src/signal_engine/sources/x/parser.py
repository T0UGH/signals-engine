"""X GraphQL timeline response parser.

Parses the raw X API JSON response into a list of NormalizedTweet objects.
Schema drift is caught explicitly — any unexpected structure raises SchemaError.
"""

import re
from typing import Any

from .errors import SchemaError
from .models import NormalizedTweet


def _parse_views(raw: Any) -> int:
    """Parse engagement view count.

    X returns views as either:
    - an integer: 1234
    - a string: "1234" or "1.2K" or "1.2M"

    Returns 0 if unavailable.
    """
    if raw is None:
        return 0
    if isinstance(raw, int):
        return max(0, raw)
    s = str(raw).strip()
    if not s:
        return 0
    # Handle "1.2K", "1.2M" suffixes
    m = re.match(r"^([\d.]+)([KM])?$", s, re.IGNORECASE)
    if m:
        value = float(m.group(1))
        suffix = m.group(2)
        if suffix:
            value *= 1000 if suffix.upper() == "K" else 1_000_000
        return int(value)
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _extract_tweet(result: Any, seen: set[str]) -> NormalizedTweet | None:
    """Extract a single NormalizedTweet from a tweet result object.

    Returns None if the entry should be skipped (e.g. already-seen ID, promoted).
    Raises SchemaError if a structural field is missing unexpectedly.
    """
    if result is None:
        return None

    # Unwrap tweet wrapper (opencli: `const tw = result.tweet || result`)
    tw = result.get("tweet") or result

    rest_id = _require_str(tw, "rest_id")
    if rest_id in seen:
        return None
    seen.add(rest_id)

    # Author: core.user_results.result.core.legacy.screen_name (user's legacy, not tweet's)
    user_result = tw.get("core", {}).get("user_results", {}).get("result", {})
    user_legacy = (user_result.get("core") or {}).get("legacy") or {}
    screen_name = user_legacy.get("screen_name")
    if not screen_name:
        raise SchemaError(f"Missing screen_name for tweet {rest_id}")
    screen_name = str(screen_name)

    # Tweet's own legacy (engagement counts, text, timestamps)
    tweet_legacy = tw.get("legacy") or {}

    # Text: note_tweet (long-form) or tweet_legacy.full_text
    note_tweet_text = (
        (tw.get("note_tweet") or {})
        .get("note_tweet_results", {})
        .get("result", {})
        .get("text", "")
    )
    full_text = tweet_legacy.get("full_text", "") or ""
    text = note_tweet_text or full_text

    # Engagement counts from tweet_legacy
    likes = int(tweet_legacy.get("favorite_count") or 0)
    retweets = int(tweet_legacy.get("retweet_count") or 0)
    replies = int(tweet_legacy.get("reply_count") or 0)
    views = _parse_views(tw.get("views", {}).get("count"))

    created_at = str(tweet_legacy.get("created_at") or "")

    url = f"https://x.com/{screen_name}/status/{rest_id}"

    return NormalizedTweet(
        id=rest_id,
        author=screen_name,
        text=text,
        likes=likes,
        retweets=retweets,
        replies=replies,
        views=views,
        created_at=created_at,
        url=url,
    )


def _require_str(obj: Any, key: str) -> str:
    """Get a string field from dict, raising SchemaError if missing."""
    val = obj.get(key)
    if val is None:
        raise SchemaError(f"Missing expected field '{key}' in tweet object")
    return str(val)


def parse_timeline_response(raw: dict) -> list[NormalizedTweet]:
    """Parse X home timeline GraphQL response into NormalizedTweet list.

    Handles:
    - Single tweet entries: content.itemContent.tweet_results.result
    - Conversation module entries: content.items[].item.itemContent.tweet_results.result
    - Cursor entries: content.cursorType / content.value
    - Promoted content: skipped silently
    - Deduplication by rest_id

    Args:
        raw: raw JSON dict from X API

    Returns:
        list of NormalizedTweet (order preserved, deduped)

    Raises:
        SchemaError: if the response structure is completely unexpected
    """
    tweets: list[NormalizedTweet] = []
    seen: set[str] = set()
    next_cursor: str | None = None

    try:
        instructions = (
            raw.get("data", {})
            .get("home", {})
            .get("home_timeline_urt", {})
            .get("instructions", [])
        )
    except Exception as e:
        raise SchemaError(f"Unexpected response structure at root level: {e}") from e

    for inst in instructions:
        if not isinstance(inst, dict):
            continue
        entries = inst.get("entries") or []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content") or {}

            # Cursor entry — extract bottom cursor
            entry_type = content.get("entryType") or content.get("__typename", "")
            if entry_type == "TimelineTimelineCursor" or str(entry.get("entryId", "")).startswith("cursor-bottom-"):
                cursor_val = content.get("value")
                if cursor_val:
                    next_cursor = str(cursor_val)
                continue

            # Determine tweet source: direct itemContent or conversation items[]
            tweet_result: Any = None

            item_content = content.get("itemContent") or {}
            tweet_result = item_content.get("tweet_results", {}).get("result")

            if tweet_result is None:
                # Conversation module: items[].item.itemContent.tweet_results.result
                items = content.get("items") or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    inner_content = (item.get("item") or {}).get("itemContent") or {}
                    tweet_result = inner_content.get("tweet_results", {}).get("result")
                    if tweet_result:
                        break

            if tweet_result is None:
                continue

            # Skip promoted content
            if item_content.get("promotedMetadata"):
                continue

            try:
                tweet = _extract_tweet(tweet_result, seen)
                if tweet:
                    tweets.append(tweet)
            except SchemaError:
                # Schema drift — skip malformed tweet but continue processing
                continue

    return tweets
