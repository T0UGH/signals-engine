"""X auth mode resolution and legacy cookie-file loading."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import AuthError

# Hardcoded Bearer token — URL-decoded from opencli timeline.ts HOME_TIMELINE_BEARER_TOKEN.
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8"
    "LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Required cookies for X GraphQL API
_REQUIRED_COOKIES = {"auth_token", "ct0"}
DEFAULT_BROWSER_SESSION_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_BROWSER_SESSION_TARGET_URL = "https://x.com"


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


@dataclass(frozen=True)
class BrowserSessionAuthConfig:
    """Browser-session auth resolved from lane config.

    The preferred workflow is attaching to an already logged-in host browser
    over CDP. Operators can still point this at an isolated browser instance
    when they explicitly want separation.
    """

    mode: str
    cdp_url: str
    target_url: str
    reuse_existing_page: bool = True


@dataclass(frozen=True)
class CookieFileAuthConfig:
    """Legacy cookie-file auth resolved from lane config."""

    mode: str
    cookie_file: str | None = None


def default_cookie_file_path(home: Path | None = None) -> Path:
    """Return the default legacy cookie-file path."""
    return (home or Path.home()) / ".signal-engine" / "x-cookies.json"


def resolve_auth_config(
    auth_config: Mapping[str, object] | None,
    *,
    cookie_file: str | Path | None = None,
) -> BrowserSessionAuthConfig | CookieFileAuthConfig:
    """Resolve X auth mode from config.

    Browser-session is the preferred/default mode and assumes reuse of an
    already logged-in browser session when available. A legacy `cookie_file`
    value without an explicit mode is still treated as cookie-file mode for
    backwards compatibility.
    """

    merged = dict(auth_config or {})
    legacy_cookie_file = merged.get("cookie_file")
    if not legacy_cookie_file and cookie_file is not None:
        legacy_cookie_file = cookie_file

    mode = str(merged.get("mode") or "").strip().lower()
    if not mode:
        mode = "cookie-file" if legacy_cookie_file else "browser-session"

    if mode == "browser-session":
        cdp_url = str(merged.get("cdp_url") or DEFAULT_BROWSER_SESSION_CDP_URL).strip()
        target_url = str(merged.get("target_url") or DEFAULT_BROWSER_SESSION_TARGET_URL).strip()
        if not cdp_url:
            raise AuthError("Browser-session auth requires a non-empty cdp_url.")
        if not target_url:
            raise AuthError("Browser-session auth requires a non-empty target_url.")
        return BrowserSessionAuthConfig(
            mode=mode,
            cdp_url=cdp_url,
            target_url=target_url,
            reuse_existing_page=bool(merged.get("reuse_existing_page", True)),
        )

    if mode == "cookie-file":
        resolved_cookie_file = None
        if legacy_cookie_file:
            resolved_cookie_file = str(Path(legacy_cookie_file).expanduser())
        return CookieFileAuthConfig(mode=mode, cookie_file=resolved_cookie_file)

    raise AuthError(
        f"Unsupported X auth mode '{mode}'. Expected 'browser-session' or 'cookie-file'."
    )


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
