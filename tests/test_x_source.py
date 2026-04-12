"""Tests for the X source subsystem (auth, parser, models)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signals_engine.sources.x import (
    NormalizedTweet,
    AuthError,
    SchemaError,
)
from signals_engine.sources.x.auth import load_auth, auth_to_cookie_header, XAuth
from signals_engine.sources.x.parser import parse_timeline_response, _parse_views


class TestParseViews(unittest.TestCase):
    def test_int(self):
        self.assertEqual(_parse_views(1234), 1234)

    def test_str_int(self):
        self.assertEqual(_parse_views("1234"), 1234)

    def test_str_k_suffix(self):
        self.assertEqual(_parse_views("1.2K"), 1200)

    def test_str_m_suffix(self):
        self.assertEqual(_parse_views("3.5M"), 3_500_000)

    def test_str_m_lowercase(self):
        self.assertEqual(_parse_views("2.1m"), 2_100_000)

    def test_str_k_uppercase(self):
        self.assertEqual(_parse_views("500K"), 500_000)

    def test_none(self):
        self.assertEqual(_parse_views(None), 0)

    def test_empty_string(self):
        self.assertEqual(_parse_views(""), 0)

    def test_whitespace(self):
        self.assertEqual(_parse_views("   "), 0)


class TestParseTimelineResponse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = Path(__file__).parent / "fixtures" / "x-timeline-sample.json"
        with open(fixture_path) as f:
            cls.raw = json.load(f)

    def test_parses_two_tweets(self):
        tweets = parse_timeline_response(self.raw)
        self.assertEqual(len(tweets), 2)

    def test_tweet_ids(self):
        tweets = parse_timeline_response(self.raw)
        ids = [t.id for t in tweets]
        self.assertIn("1234567890", ids)
        self.assertIn("9876543210", ids)

    def test_tweet_authors(self):
        tweets = parse_timeline_response(self.raw)
        authors = {t.author for t in tweets}
        self.assertEqual(authors, {"testuser", "another_dev"})

    def test_engagement_counts_tweet1(self):
        tweets = parse_timeline_response(self.raw)
        t = next(t for t in tweets if t.id == "1234567890")
        self.assertEqual(t.likes, 42)
        self.assertEqual(t.retweets, 10)
        self.assertEqual(t.replies, 5)

    def test_engagement_counts_tweet2(self):
        tweets = parse_timeline_response(self.raw)
        t = next(t for t in tweets if t.id == "9876543210")
        self.assertEqual(t.likes, 99)
        self.assertEqual(t.retweets, 20)
        self.assertEqual(t.replies, 8)

    def test_views_string_format(self):
        tweets = parse_timeline_response(self.raw)
        t = next(t for t in tweets if t.id == "1234567890")
        self.assertEqual(t.views, 1234)

    def test_views_int_format(self):
        tweets = parse_timeline_response(self.raw)
        t = next(t for t in tweets if t.id == "9876543210")
        self.assertEqual(t.views, 5678)

    def test_note_tweet_text(self):
        """Long-form note tweet text is used instead of legacy.full_text."""
        tweets = parse_timeline_response(self.raw)
        t = next(t for t in tweets if t.id == "9876543210")
        self.assertIn("note_tweet", t.text)
        self.assertNotIn("GM!", t.text)

    def test_regular_full_text(self):
        """Legacy full_text is used when note_tweet is absent."""
        tweets = parse_timeline_response(self.raw)
        t = next(t for t in tweets if t.id == "1234567890")
        self.assertIn("test tweet from fixture data", t.text)

    def test_url_format(self):
        tweets = parse_timeline_response(self.raw)
        t = next(t for t in tweets if t.id == "1234567890")
        self.assertEqual(t.url, "https://x.com/testuser/status/1234567890")

    def test_created_at_not_empty(self):
        tweets = parse_timeline_response(self.raw)
        for t in tweets:
            self.assertTrue(t.created_at)

    def test_deduplication(self):
        """Same ID appearing twice should only produce one tweet."""
        raw = json.loads(json.dumps(self.raw))
        # Add a duplicate entry
        entries = raw["data"]["home"]["home_timeline_urt"]["instructions"][0]["entries"]
        dup = json.loads(json.dumps(entries[1]))  # deep copy
        dup["entryId"] = "tweet-1234567890-duplicate"
        entries.append(dup)

        tweets = parse_timeline_response(raw)
        ids = [t.id for t in tweets]
        self.assertEqual(ids.count("1234567890"), 1)


class TestNormalizedTweet(unittest.TestCase):
    def test_all_fields(self):
        t = NormalizedTweet(
            id="123",
            author="testuser",
            text="Hello world",
            likes=10,
            retweets=2,
            replies=1,
            views=100,
            created_at="Mon Apr 06 10:00:00 +0000 2026",
            url="https://x.com/testuser/status/123",
        )
        self.assertEqual(t.id, "123")
        self.assertEqual(t.author, "testuser")
        self.assertEqual(t.likes, 10)
        self.assertEqual(t.retweets, 2)


class TestLoadAuth(unittest.TestCase):
    def test_netscape_format(self):
        """Netscape format cookie file is parsed correctly."""
        content = (
            ".x.com\tTRUE\t/\tTRUE\t9999999999\tauth_token\ttest_auth_value\n"
            ".x.com\tTRUE\t/\tTRUE\t9999999999\tct0\ttest_csrf_value\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            path = f.name

        try:
            auth = load_auth(path)
            self.assertEqual(auth.cookies["auth_token"], "test_auth_value")
            self.assertEqual(auth.cookies["ct0"], "test_csrf_value")
            self.assertTrue(auth.bearer_token)  # bearer is populated
        finally:
            os.unlink(path)

    def test_json_format(self):
        """JSON format cookie file is parsed correctly (array-of-objects format)."""
        content = json.dumps({
            "cookies": [
                {"name": "auth_token", "value": "json_auth"},
                {"name": "ct0", "value": "json_csrf"},
            ]
        })
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(content)
            f.flush()
            path = f.name

        try:
            auth = load_auth(path)
            self.assertEqual(auth.cookies["auth_token"], "json_auth")
            self.assertEqual(auth.cookies["ct0"], "json_csrf")
            self.assertTrue(auth.bearer_token)  # bearer is populated
        finally:
            os.unlink(path)

    def test_missing_auth_token(self):
        """Missing auth_token raises AuthError."""
        content = ".x.com\tTRUE\t/\tTRUE\t9999999999\tct0\tcsrf_only\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            path = f.name

        try:
            with self.assertRaises(AuthError) as ctx:
                load_auth(path)
            self.assertIn("auth_token", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_missing_ct0(self):
        """Missing ct0 raises AuthError."""
        content = ".x.com\tTRUE\t/\tTRUE\t9999999999\tauth_token\tauth_only\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            path = f.name

        try:
            with self.assertRaises(AuthError) as ctx:
                load_auth(path)
            self.assertIn("ct0", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_empty_cookie_value_json(self):
        """Empty string cookie value in JSON format raises AuthError."""
        content = json.dumps({
            "cookies": [
                {"name": "auth_token", "value": ""},
                {"name": "ct0", "value": "test_csrf"},
            ]
        })
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(content)
            f.flush()
            path = f.name

        try:
            with self.assertRaises(AuthError) as ctx:
                load_auth(path)
            self.assertIn("is empty", str(ctx.exception))
        finally:
            os.unlink(path)


class TestAuthToCookieHeader(unittest.TestCase):
    def test_format(self):
        auth = XAuth(
            cookies={"auth_token": "abc123", "ct0": "xyz789"},
            bearer_token="dummy_bearer",
        )
        header = auth_to_cookie_header(auth)
        self.assertIn("auth_token=abc123", header)
        self.assertIn("ct0=xyz789", header)
        self.assertIn(";", header)


class TestClientErrors(unittest.TestCase):
    """Tests for XClient HTTP error classification."""

    def _make_auth(self) -> XAuth:
        return XAuth(
            cookies={"auth_token": "test_auth", "ct0": "test_csrf"},
            bearer_token="test_bearer",
        )

    def test_401_raises_auth_error(self):
        """HTTP 401 raises AuthError, not NameError."""
        import httpx
        from signals_engine.sources.x.client import XClient

        auth = self._make_auth()
        client = XClient(auth, timeout=5)

        # httpx mock that returns 401
        class FakeResponse:
            status_code = 401
            def raise_for_status(self):
                pass

        with patch.object(httpx.Client, "get", return_value=FakeResponse()):
            with self.assertRaises(AuthError) as ctx:
                client.fetch_timeline_raw("c-CzHF1LboFilMpsx4ZCrQ", "HomeTimeline", count=1, cursor=None)
            # Must NOT mention undefined variable
            self.assertNotIn("NameError", str(type(ctx.exception)))
            self.assertIn("401", str(ctx.exception))

    def test_429_raises_rate_limit_error(self):
        """HTTP 429 raises RateLimitError."""
        import httpx
        from signals_engine.sources.x.client import XClient

        auth = self._make_auth()
        client = XClient(auth, timeout=5)

        class FakeResponse:
            status_code = 429
            def json(self):
                return {}

        with patch.object(httpx.Client, "get", return_value=FakeResponse()):
            with self.assertRaises(Exception) as ctx:
                client.fetch_timeline_raw("c-CzHF1LboFilMpsx4ZCrQ", "HomeTimeline", count=1, cursor=None)
            from signals_engine.sources.x.errors import RateLimitError
            self.assertIsInstance(ctx.exception, RateLimitError)

    def test_500_raises_source_unavailable(self):
        """HTTP 5xx raises SourceUnavailableError."""
        import httpx
        from signals_engine.sources.x.client import XClient

        auth = self._make_auth()
        client = XClient(auth, timeout=5)

        class FakeResponse:
            status_code = 503
            def json(self):
                return {}

        with patch.object(httpx.Client, "get", return_value=FakeResponse()):
            with self.assertRaises(Exception) as ctx:
                client.fetch_timeline_raw("c-CzHF1LboFilMpsx4ZCrQ", "HomeTimeline", count=1, cursor=None)
            from signals_engine.sources.x.errors import SourceUnavailableError
            self.assertIsInstance(ctx.exception, SourceUnavailableError)

    def test_timeout_raises_transport_error(self):
        """Request timeout raises TransportError."""
        import httpx
        from signals_engine.sources.x.client import XClient

        auth = self._make_auth()
        client = XClient(auth, timeout=5)

        with patch.object(httpx.Client, "get", side_effect=httpx.TimeoutException("timeout")):
            with self.assertRaises(Exception) as ctx:
                client.fetch_timeline_raw("c-CzHF1LboFilMpsx4ZCrQ", "HomeTimeline", count=1, cursor=None)
            from signals_engine.sources.x.errors import TransportError
            self.assertIsInstance(ctx.exception, TransportError)
            self.assertIn("timed out", str(ctx.exception))


class TestSchemaDrift(unittest.TestCase):
    """Tests for schema drift handling — SchemaError must propagate."""

    def test_missing_rest_id_raises_schema_error(self):
        """Tweet missing rest_id raises SchemaError (not silently skipped)."""
        raw = {
            "data": {
                "home": {
                    "home_timeline_urt": {
                        "instructions": [
                            {
                                "type": "TimelineAddEntries",
                                "entries": [
                                    {
                                        "entryId": "tweet-1",
                                        "sortIndex": "999",
                                        "content": {
                                            "entryType": "TimelineTimelineItem",
                                            "itemContent": {
                                                "__typename": "TimelineTweetItem",
                                                "tweet_results": {
                                                    "result": {
                                                        "__typename": "Tweet",
                                                        # Missing rest_id
                                                        "core": {
                                                            "user_results": {
                                                                "result": {
                                                                    "__typename": "User",
                                                                    "id": "123",
                                                                    "core": {
                                                                        "legacy": {
                                                                            "screen_name": "testuser",
                                                                        }
                                                                    },
                                                                    "legacy": {
                                                                        "screen_name": "testuser",
                                                                    }
                                                                }
                                                            }
                                                        },
                                                        "legacy": {
                                                            "full_text": "test",
                                                            "created_at": "Mon Apr 06 10:00:00 +0000 2026",
                                                        },
                                                    }
                                                }
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }
        from signals_engine.sources.x.parser import SchemaError
        with self.assertRaises(SchemaError):
            parse_timeline_response(raw)

    def test_schema_error_not_silently_swallowed(self):
        """SchemaError from _extract_tweet must propagate, not be silently caught."""
        # A malformed entry (missing screen_name) in a response with valid entries
        raw = {
            "data": {
                "home": {
                    "home_timeline_urt": {
                        "instructions": [
                            {
                                "type": "TimelineAddEntries",
                                "entries": [
                                    {
                                        "entryId": "tweet-bad",
                                        "sortIndex": "999",
                                        "content": {
                                            "entryType": "TimelineTimelineItem",
                                            "itemContent": {
                                                "tweet_results": {
                                                    "result": {
                                                        "__typename": "Tweet",
                                                        "rest_id": "bad-id",
                                                        "core": {
                                                            "user_results": {
                                                                "result": {
                                                                    "__typename": "User",
                                                                    "id": "999",
                                                                    # Missing core.legacy.screen_name
                                                                    "legacy": {},
                                                                }
                                                            }
                                                        },
                                                        "legacy": {
                                                            "full_text": "malformed",
                                                        },
                                                    }
                                                }
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }
        from signals_engine.sources.x.parser import SchemaError
        with self.assertRaises(SchemaError) as ctx:
            parse_timeline_response(raw)
        self.assertIn("screen_name", str(ctx.exception))


class TestParseWithSeen(unittest.TestCase):
    """Tests for cross-page dedup via shared seen set."""

    def test_seen_ids_skip_already_processed(self):
        """IDs already in seen set are skipped when parsing next page."""
        raw = json.loads(json.dumps(self._get_raw_with_ids(["111", "222", "333"])))
        seen = {"111", "222"}  # 111 and 222 already processed
        tweets = parse_timeline_response(raw, seen=seen)
        # Only 333 should be returned, not 111 or 222
        ids = [t.id for t in tweets]
        self.assertEqual(ids, ["333"])

    def test_seen_ids_empty_returns_all(self):
        """Empty seen set returns all tweets."""
        raw = self._get_raw_with_ids(["aaa", "bbb"])
        tweets = parse_timeline_response(raw, seen=set())
        ids = [t.id for t in tweets]
        self.assertEqual(set(ids), {"aaa", "bbb"})

    def _get_raw_with_ids(self, ids):
        """Build a minimal timeline response with given tweet IDs."""
        entries = []
        for idx, tweet_id in enumerate(ids):
            entries.append(
                {
                    "entryId": f"tweet-{tweet_id}",
                    "sortIndex": str(1000 - idx),
                    "content": {
                        "entryType": "TimelineTimelineItem",
                        "itemContent": {
                            "tweet_results": {
                                "result": {
                                    "__typename": "Tweet",
                                    "rest_id": tweet_id,
                                    "core": {
                                        "user_results": {
                                            "result": {
                                                "__typename": "User",
                                                "id": f"uid-{tweet_id}",
                                                "core": {
                                                    "legacy": {
                                                        "screen_name": f"user{tweet_id}",
                                                    }
                                                },
                                                "legacy": {
                                                    "screen_name": f"user{tweet_id}",
                                                }
                                            }
                                        }
                                    },
                                    "legacy": {
                                        "full_text": f"Tweet {tweet_id}",
                                        "created_at": "Mon Apr 06 10:00:00 +0000 2026",
                                        "favorite_count": 0,
                                        "retweet_count": 0,
                                        "reply_count": 0,
                                    },
                                }
                            }
                        }
                    }
                }
            )
        return {
            "data": {
                "home": {
                    "home_timeline_urt": {
                        "instructions": [
                            {
                                "type": "TimelineAddEntries",
                                "entries": entries,
                            }
                        ]
                    }
                }
            }
        }


class TestTimelineCursorExtraction(unittest.TestCase):
    """Tests for cursor extraction and termination logic."""

    def test_extracts_bottom_cursor(self):
        """_extract_cursor returns the bottom cursor value."""
        from signals_engine.sources.x.feed.timeline import _extract_cursor

        raw = {
            "data": {
                "home": {
                    "home_timeline_urt": {
                        "instructions": [
                            {
                                "entries": [
                                    {
                                        "entryId": "cursor-bottom-abc123",
                                        "content": {
                                            "entryType": "TimelineTimelineCursor",
                                            "cursorType": "Bottom",
                                            "value": "abc_page_2_cursor",
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }
        cursor = _extract_cursor(raw)
        self.assertEqual(cursor, "abc_page_2_cursor")

    def test_returns_none_when_no_cursor(self):
        """_extract_cursor returns None when no bottom cursor present."""
        from signals_engine.sources.x.feed.timeline import _extract_cursor

        raw = {
            "data": {
                "home": {
                    "home_timeline_urt": {
                        "instructions": [
                            {
                                "entries": [
                                    {
                                        "entryId": "tweet-123",
                                        "content": {
                                            "entryType": "TimelineTimelineItem",
                                            "itemContent": {
                                                "tweet_results": {"result": {}}
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }
        cursor = _extract_cursor(raw)
        self.assertIsNone(cursor)


if __name__ == "__main__":
    unittest.main()
