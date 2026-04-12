"""X browser-session client using Playwright over CDP."""

from __future__ import annotations

import json
from contextlib import contextmanager
from urllib.parse import urlparse

from .auth import BEARER_TOKEN, BrowserSessionAuthConfig
from .client import build_graphql_url
from .errors import AuthError, RateLimitError, SourceUnavailableError, TransportError


def _require_playwright():
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AuthError(
            "Playwright is required for X browser-session auth. "
            "Install the 'playwright' package to use mode=browser-session."
        ) from exc
    return sync_playwright, PlaywrightError


def _host_matches(url: str, target_url: str) -> bool:
    page_host = urlparse(url).hostname or ""
    target_host = urlparse(target_url).hostname or ""
    if not page_host or not target_host:
        return False
    return page_host == target_host or page_host.endswith(f".{target_host}")


def _ensure_x_page(browser, config: BrowserSessionAuthConfig, timeout_ms: int, playwright_error):
    """Reuse an existing x.com tab when possible, else open a fresh x.com tab."""

    contexts = list(browser.contexts)
    if not contexts:
        raise AuthError(
            "Chrome is reachable over CDP but exposed no browser contexts. "
            "Keep the logged-in browser session open and try again."
        )

    if config.reuse_existing_page:
        for context in contexts:
            for page in context.pages:
                if _host_matches(page.url, config.target_url):
                    return page

    context = contexts[0]
    try:
        page = context.new_page()
        page.goto(config.target_url, wait_until="domcontentloaded", timeout=timeout_ms)
        return page
    except playwright_error as exc:
        raise AuthError(
            f"Could not open {config.target_url} in the attached browser session: {exc}"
        ) from exc


def _extract_cookie_value(cookie_string: str, name: str) -> str:
    for part in cookie_string.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        cookie_name, cookie_value = item.split("=", 1)
        if cookie_name.strip() == name:
            return cookie_value.strip()
    return ""


def _extract_ct0(page) -> str:
    cookie_string = str(page.evaluate("() => document.cookie") or "")
    ct0 = _extract_cookie_value(cookie_string, "ct0")
    if not ct0:
        raise AuthError(
            "ct0 missing from x.com browser session. Open x.com in the attached "
            "browser session and make sure the account is logged in."
        )
    return ct0


def _fetch_graphql_in_page(
    page,
    *,
    url: str,
    headers: dict[str, str],
    timeout_ms: int,
) -> dict:
    result = page.evaluate(
        """
        async ({ url, headers, timeoutMs }) => {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), timeoutMs);
          try {
            const response = await fetch(url, {
              method: 'GET',
              headers,
              credentials: 'include',
              signal: controller.signal,
            });
            const text = await response.text();
            return { status: response.status, text };
          } catch (error) {
            return {
              error: error instanceof Error ? error.message : String(error),
            };
          } finally {
            clearTimeout(timer);
          }
        }
        """,
        {
            "url": url,
            "headers": headers,
            "timeoutMs": timeout_ms,
        },
    )

    if result.get("error"):
        raise TransportError(f"Browser-session fetch failed: {result['error']}")

    status = int(result.get("status") or 0)
    text = str(result.get("text") or "")
    if status in {401, 403}:
        raise AuthError(
            f"Browser-session X request failed with HTTP {status}. "
            "Refresh x.com in the attached logged-in browser session and try again."
        )
    if status == 429:
        raise RateLimitError(
            "HTTP 429 Too Many Requests — X is rate-limiting this browser session. "
            "Wait before retrying."
        )
    if status >= 500:
        raise SourceUnavailableError(
            f"X server error: HTTP {status}. Temporarily unavailable."
        )
    if status < 200 or status >= 300:
        raise TransportError(f"Unexpected HTTP {status} from X browser-session fetch.")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TransportError("X browser-session fetch returned invalid JSON.") from exc


@contextmanager
def browser_page_session(config: BrowserSessionAuthConfig, timeout: int):
    """Yield an x.com page from a live browser session attached over CDP."""

    sync_playwright, playwright_error = _require_playwright()
    timeout_ms = timeout * 1000

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(
                config.cdp_url,
                timeout=timeout_ms,
            )
            yield _ensure_x_page(browser, config, timeout_ms, playwright_error)
        except AuthError:
            raise
        except playwright_error as exc:
            raise AuthError(
                f"Could not connect to browser session at {config.cdp_url}: {exc}"
            ) from exc


class XBrowserSessionClient:
    """Fetch X GraphQL responses inside a live browser session."""

    def __init__(self, config: BrowserSessionAuthConfig, timeout: int = 30):
        self.config = config
        self.timeout = timeout

    def fetch_timeline_raw(
        self,
        query_id: str,
        operation_name: str,
        count: int = 40,
        cursor: str | None = None,
        extra_variables: dict | None = None,
    ) -> dict:
        url = build_graphql_url(
            query_id=query_id,
            operation_name=operation_name,
            count=count,
            cursor=cursor,
            extra_variables=extra_variables,
        )

        with browser_page_session(self.config, self.timeout) as page:
            ct0 = _extract_ct0(page)
            headers = {
                "Authorization": f"Bearer {BEARER_TOKEN}",
                "X-Csrf-Token": ct0,
                "X-Twitter-Auth-Type": "OAuth2Session",
                "X-Twitter-Active-User": "yes",
                "Accept": "application/json",
            }
            return _fetch_graphql_in_page(
                page,
                url=url,
                headers=headers,
                timeout_ms=self.timeout * 1000,
            )
