"""Tests for x-feed lane collect."""
import unittest
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signal_engine.core import RunContext, RunStatus, SignalRecord
from signal_engine.lanes.x_feed import collect_x_feed, _sanitize_handle, _make_session_id
from signal_engine.signals.render import render_signal_markdown


SAMPLE_TWEETS = [
    {
        "id": "123456789",
        "author": "testuser",
        "text": "Hello world! This is a test tweet with some content.",
        "likes": 42,
        "retweets": 10,
        "replies": 5,
        "views": 1000,
        "created_at": "2026-04-06T10:00:00Z",
        "url": "https://x.com/testuser/status/123456789",
    },
    {
        "id": "987654321",
        "author": "another_dev",
        "text": "GM! Building something cool.",
        "likes": 99,
        "retweets": 20,
        "replies": 8,
        "views": 5000,
        "created_at": "2026-04-06T11:00:00Z",
        "url": "https://x.com/another_dev/status/987654321",
    },
]


class TestSanitizeHandle(unittest.TestCase):
    def test_sanitize_basic(self):
        self.assertEqual(_sanitize_handle("testuser"), "testuser")

    def test_sanitize_with_slash(self):
        self.assertEqual(_sanitize_handle("user/name"), "user_name")

    def test_sanitize_with_colon(self):
        self.assertEqual(_sanitize_handle("user:name"), "user_name")


class TestMakeSessionId(unittest.TestCase):
    def test_session_id_format(self):
        sid = _make_session_id("2026-04-06")
        self.assertTrue(sid.startswith("feed-2026-04-06-"))
        self.assertEqual(len(sid), len("feed-2026-04-06-") + 6)


class TestSignalRecordMapping(unittest.TestCase):
    def test_signal_record_from_tweet(self):
        """Test that a tweet dict maps correctly to SignalRecord fields."""
        tweet = SAMPLE_TWEETS[0]
        # Simulate what x_feed.py does
        record = SignalRecord(
            lane="x-feed",
            signal_type="feed-exposure",
            source="x",
            entity_type="author",
            entity_id=tweet["author"],
            title=f"@{tweet['author']} #1",
            source_url=tweet["url"],
            fetched_at="2026-04-06T12:00:00Z",
            file_path="/tmp/test.md",
            handle=tweet["author"],
            post_id=tweet["id"],
            created_at=tweet["created_at"],
            position=1,
            text_preview=tweet["text"][:120],
            likes=tweet["likes"],
            retweets=tweet["retweets"],
            replies=tweet["replies"],
            views=tweet["views"],
        )
        self.assertEqual(record.signal_type, "feed-exposure")
        self.assertEqual(record.handle, "testuser")
        self.assertEqual(record.likes, 42)
        self.assertEqual(record.views, 1000)
        self.assertEqual(record.position, 1)


class TestSignalMarkdown(unittest.TestCase):
    def test_render_x_feed_signal(self):
        record = SignalRecord(
            lane="x-feed",
            signal_type="feed-exposure",
            source="x",
            entity_type="author",
            entity_id="testuser",
            title="@testuser #1",
            source_url="https://x.com/testuser/status/123",
            fetched_at="2026-04-06T12:00:00Z",
            file_path="/tmp/test.md",
            handle="testuser",
            post_id="123",
            created_at="2026-04-06T10:00:00Z",
            position=1,
            text_preview="GM!",
            likes=42,
            retweets=10,
            replies=5,
            views=1000,
        )
        md = render_signal_markdown(record)
        self.assertIn("type: feed-exposure", md)
        self.assertIn("handle: testuser", md)
        self.assertIn("post_id: '123'", md)
        self.assertIn("## Post", md)
        self.assertIn("GM!", md)
        self.assertIn("## Engagement", md)
        self.assertIn("Likes: 42", md)
        self.assertIn("## Feed Context", md)
        self.assertIn("Position in session: #1", md)


if __name__ == "__main__":
    unittest.main()
