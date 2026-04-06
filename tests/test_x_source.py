"""Tests for the X source subsystem (auth, parser, models)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signal_engine.sources.x import (
    NormalizedTweet,
    AuthError,
    SchemaError,
)
from signal_engine.sources.x.auth import load_auth, auth_to_cookie_header, XAuth
from signal_engine.sources.x.parser import parse_timeline_response, _parse_views


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


if __name__ == "__main__":
    unittest.main()
