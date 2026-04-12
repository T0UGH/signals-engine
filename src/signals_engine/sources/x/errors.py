"""X source error types."""


class XSourceError(Exception):
    """Base exception for all X source errors."""

    pass


class AuthError(XSourceError):
    """Auth material is missing, malformed, or invalid.

    Examples: cookie file not found, missing required cookies (auth_token, ct0),
    cookie file parse failure, browser-session CDP unreachable, missing ct0.
    """

    pass


class TransportError(XSourceError):
    """Network transport failure.

    Examples: connection refused, DNS resolution failed, socket timeout.
    """

    pass


class RateLimitError(XSourceError):
    """X API rate limit hit (HTTP 429).

    The client should back off and retry later.
    """

    pass


class SchemaError(XSourceError):
    """X API response structure doesn't match expected schema.

    This usually means X has changed its GraphQL response format and the
    parser needs to be updated.
    """

    pass


class SourceUnavailableError(XSourceError):
    """X source is temporarily unavailable.

    Examples: HTTP 503, 5xx server errors.
    """

    pass
