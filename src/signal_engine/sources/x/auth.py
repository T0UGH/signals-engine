"""X authentication via cookie file.

Loads and validates X.com login cookies from a cookie file.
Supports Netscape format (used by curl, yt-dlp) and JSON format.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import AuthError

# Hardcoded Bearer token — URL-decoded from opencli timeline.ts HOME_TIMELINE_BEARER_TOKEN.
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8"
    "LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Required cookies for X GraphQL API
_REQUIRED_COOKIES = {"auth_token", "ct0"}


@dataclass
class XAuth:
    """Validated X authentication state.

    Attributes:
        cookies: dict mapping cookie name -> cookie value, ready to inject as
                Cookie header (e.g. "auth_token=abc; ct0=def").
        bearer_token: hardcoded Twitter Bearer token.
    """

    cookies: dict[str, str]
    bearer_token: str


def load_auth(cookie_file: str | Path) -> XAuth:
    """Load and validate X authentication from a cookie file.

    Supports two formats:
        - Netscape format (one line per cookie, tab-separated fields)
        - JSON format ({"cookies": [{"name": "...", "value": "..."}, ...]})

    Args:
        cookie_file: Path to the cookie file.

    Returns:
        XAuth with validated cookies and bearer token.

    Raises:
        AuthError: if the file does not exist, cannot be parsed,
                   or is missing required cookies (auth_token, ct0).
    """
    path = Path(cookie_file).expanduser()

    if not path.exists():
        raise AuthError(f"Cookie file not found: {path}")

    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as e:
        raise AuthError(f"Cannot read cookie file {path}: {e}") from e

    if not content:
        raise AuthError(f"Cookie file is empty: {path}")

    # Try JSON first, fall back to Netscape
    cookies: dict[str, str] = {}

    if content.startswith("{"):
        # JSON format: {"cookies": [{"name": "...", "value": "..."}, ...]}
        try:
            data = json.loads(content)
            cookie_list = data.get("cookies", [])
            for entry in cookie_list:
                name = entry.get("name", "")
                value = entry.get("value", "")
                if name:
                    cookies[name] = value
        except json.JSONDecodeError as e:
            raise AuthError(f"Cookie file is not valid JSON: {path}: {e}") from e
    else:
        # Netscape format
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 7:
                continue
            name = fields[5].strip()
            value = fields[6].strip()
            if name and value:
                cookies[name] = value

    # Validate required cookies
    missing = _REQUIRED_COOKIES - set(cookies.keys())
    if missing:
        raise AuthError(
            f"Cookie file is missing required cookies {sorted(missing)}: {path}. "
            f"Please export fresh cookies from a logged-in X.com session."
        )

    # Verify cookies are non-empty
    for name in _REQUIRED_COOKIES:
        if not cookies.get(name):
            raise AuthError(
                f"Cookie '{name}' in {path} is empty. "
                f"Please export fresh cookies from a logged-in X.com session."
            )

    return XAuth(cookies=cookies, bearer_token=BEARER_TOKEN)


def auth_to_cookie_header(auth: XAuth) -> str:
    """Format XAuth cookies into a Cookie header value."""
    return "; ".join(f"{name}={value}" for name, value in auth.cookies.items())
