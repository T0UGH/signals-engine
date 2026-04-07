"""X (Twitter) data sources.

Public exports:
    NormalizedTweet: canonical tweet model
    XSourceError: base error type
    AuthError, TransportError, RateLimitError, SchemaError, SourceUnavailableError
    fetch_home_timeline: entry point for the x-feed lane
    fetch_following_timeline: entry point for the x-following lane
"""

from .errors import (
    XSourceError,
    AuthError,
    TransportError,
    RateLimitError,
    SchemaError,
    SourceUnavailableError,
)
from .models import NormalizedTweet
from .feed.timeline import fetch_home_timeline
from .following.timeline import fetch_following_timeline

__all__ = [
    "NormalizedTweet",
    "XSourceError",
    "AuthError",
    "TransportError",
    "RateLimitError",
    "SchemaError",
    "SourceUnavailableError",
    "fetch_home_timeline",
    "fetch_following_timeline",
]
