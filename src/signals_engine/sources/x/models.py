"""X source data models.

These are the internal data structures used within the X source subsystem.
Lane code does not depend on these directly — it only receives the output
of timeline.fetch_home_timeline(), which returns NormalizedTweet objects.
"""

from dataclasses import dataclass


@dataclass
class NormalizedTweet:
    """A normalized tweet from the X home timeline.

    This is the source subsystem's canonical output format. The x-feed lane
    maps these fields into SignalRecord.

    All timestamps are UTC ISO8601 strings (e.g. "2026-04-06T10:00:00+0000").
    Engagement counts are integers. Missing/null counts are 0.
    """

    id: str
    """X REST ID (e.g. "2040606134050967716")."""

    author: str
    """Author screen_name without @ (e.g. "elonmusk")."""

    text: str
    """Tweet text content. May be truncated to 280 chars by X API."""

    likes: int
    """Like count (from Twitter API, may be approximate)."""

    retweets: int
    """Retweet count."""

    replies: int
    """Reply count."""

    views: int
    """View count (from Twitter API, may be approximate or -1 if unavailable)."""

    created_at: str
    """ISO8601 UTC timestamp when the tweet was created."""

    url: str
    """Permanent URL to the tweet (https://x.com/{author}/status/{id})."""
