"""X (Twitter) data sources.

Public exports:
    NormalizedTweet: canonical tweet model
    XSourceError: base error type
    AuthError, TransportError, RateLimitError, SchemaError, SourceUnavailableError
    fetch_home_timeline: primary entry point for the x-feed lane (added in Task D)
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
from .timeline import fetch_home_timeline

__all__ = [
    "NormalizedTweet",
    "XSourceError",
    "AuthError",
    "TransportError",
    "RateLimitError",
    "SchemaError",
    "SourceUnavailableError",
    "fetch_home_timeline",
]
