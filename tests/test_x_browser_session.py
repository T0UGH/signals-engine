"""Tests for X browser-session auth and mode dispatch."""

import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signals_engine.sources.x.auth import (
    BrowserSessionAuthConfig,
    CookieFileAuthConfig,
    XAuth,
    resolve_auth_config,
)
from signals_engine.sources.x.browser_session import XBrowserSessionClient
from signals_engine.sources.x.errors import AuthError
from signals_engine.sources.x.feed.timeline import fetch_home_timeline
from signals_engine.sources.x.following.timeline import fetch_following_timeline


@contextmanager
def _page_session(page):
    yield page


class _FakePage:
    def __init__(self, *, cookie_string: str, fetch_result: dict):
        self.cookie_string = cookie_string
        self.fetch_result = fetch_result
        self.scripts: list[str] = []
        self.payloads: list[dict | None] = []

    def evaluate(self, script, payload=None):
        self.scripts.append(script)
        self.payloads.append(payload)
        if "document.cookie" in script:
            return self.cookie_string
        return self.fetch_result


class TestResolveAuthConfig(unittest.TestCase):
    def test_defaults_to_browser_session_mode(self):
        auth = resolve_auth_config({})
        self.assertIsInstance(auth, BrowserSessionAuthConfig)
        self.assertEqual(auth.mode, "browser-session")
        self.assertEqual(auth.cdp_url, "http://127.0.0.1:9222")
        self.assertEqual(auth.target_url, "https://x.com")
        self.assertTrue(auth.reuse_existing_page)

    def test_legacy_cookie_file_config_uses_cookie_file_mode(self):
        auth = resolve_auth_config({"cookie_file": "/tmp/x-cookies.json"})
        self.assertIsInstance(auth, CookieFileAuthConfig)
        self.assertEqual(auth.mode, "cookie-file")
        self.assertEqual(auth.cookie_file, "/tmp/x-cookies.json")


class TestBrowserSessionClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = Path(__file__).parent / "fixtures" / "x-timeline-sample.json"
        cls.raw = json.loads(fixture_path.read_text(encoding="utf-8"))

    @patch("signals_engine.sources.x.browser_session.browser_page_session")
    def test_fetch_timeline_raw_uses_page_context_session(self, mock_page_session):
        page = _FakePage(
            cookie_string="foo=bar; ct0=test_csrf; auth_token=test_auth",
            fetch_result={"status": 200, "text": json.dumps(self.raw)},
        )
        mock_page_session.return_value = _page_session(page)

        client = XBrowserSessionClient(
            BrowserSessionAuthConfig(
                mode="browser-session",
                cdp_url="http://127.0.0.1:9222",
                target_url="https://x.com",
                reuse_existing_page=True,
            ),
            timeout=5,
        )

        raw = client.fetch_timeline_raw(
            query_id="c-CzHF1LboFilMpsx4ZCrQ",
            operation_name="HomeTimeline",
            count=2,
            cursor=None,
            extra_variables={"latestControlAvailable": True},
        )

        self.assertEqual(
            raw["data"]["home"]["home_timeline_urt"]["instructions"],
            self.raw["data"]["home"]["home_timeline_urt"]["instructions"],
        )
        fetch_payloads = [payload for payload in page.payloads if payload]
        self.assertTrue(fetch_payloads)
        self.assertEqual(fetch_payloads[-1]["headers"]["X-Csrf-Token"], "test_csrf")

    @patch("signals_engine.sources.x.browser_session.browser_page_session")
    def test_fetch_timeline_raw_missing_ct0_raises_auth_error(self, mock_page_session):
        page = _FakePage(
            cookie_string="foo=bar; auth_token=test_auth",
            fetch_result={"status": 200, "text": "{}"},
        )
        mock_page_session.return_value = _page_session(page)

        client = XBrowserSessionClient(
            BrowserSessionAuthConfig(
                mode="browser-session",
                cdp_url="http://127.0.0.1:9222",
                target_url="https://x.com",
                reuse_existing_page=True,
            ),
            timeout=5,
        )

        with self.assertRaises(AuthError) as ctx:
            client.fetch_timeline_raw(
                query_id="c-CzHF1LboFilMpsx4ZCrQ",
                operation_name="HomeTimeline",
                count=1,
            )
        self.assertIn("ct0", str(ctx.exception))


class TestTimelineAuthModeDispatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = Path(__file__).parent / "fixtures" / "x-timeline-sample.json"
        cls.raw = json.loads(fixture_path.read_text(encoding="utf-8"))

    @patch("signals_engine.sources.x.feed.timeline.XBrowserSessionClient.fetch_timeline_raw")
    def test_fetch_home_timeline_browser_session_mode(self, mock_fetch):
        mock_fetch.return_value = self.raw

        tweets = fetch_home_timeline(
            limit=2,
            auth_config={
                "mode": "browser-session",
                "cdp_url": "http://127.0.0.1:9222",
            },
            timeout=7,
        )

        self.assertEqual(len(tweets), 2)
        mock_fetch.assert_called_once()

    @patch("signals_engine.sources.x.feed.timeline.XClient.fetch_timeline_raw")
    @patch("signals_engine.sources.x.feed.timeline.load_auth")
    def test_fetch_home_timeline_cookie_file_mode(self, mock_load_auth, mock_fetch):
        mock_load_auth.return_value = XAuth(
            cookies={"auth_token": "legacy_auth", "ct0": "legacy_csrf"},
            bearer_token="legacy_bearer",
        )
        mock_fetch.return_value = self.raw

        tweets = fetch_home_timeline(
            limit=1,
            auth_config={
                "mode": "cookie-file",
                "cookie_file": "/tmp/legacy-x-cookies.json",
            },
            timeout=7,
        )

        self.assertEqual(len(tweets), 1)
        mock_load_auth.assert_called_once_with("/tmp/legacy-x-cookies.json")
        mock_fetch.assert_called_once()

    @patch("signals_engine.sources.x.following.timeline.XBrowserSessionClient.fetch_timeline_raw")
    def test_fetch_following_timeline_browser_session_mode(self, mock_fetch):
        mock_fetch.return_value = self.raw

        tweets = fetch_following_timeline(
            limit=2,
            auth_config={"mode": "browser-session"},
            timeout=7,
        )

        self.assertEqual(len(tweets), 2)
        mock_fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
