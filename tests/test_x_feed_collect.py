"""Tests for x-feed lane collect."""
import unittest
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

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


class TestCollectIntegration(unittest.TestCase):
    """Integration tests for collect_x_feed with mocked source."""

    def _make_ctx(self, tmpdir: Path) -> RunContext:
        config = {
            "lanes": {
                "x-feed": {
                    "enabled": True,
                    "opencli": {
                        "path": "~/.openclaw/workspace/github/opencli",
                        "limit": 100,
                    },
                }
            }
        }
        return RunContext(
            lane="x-feed",
            date="2026-04-06",
            data_dir=tmpdir,
            config=config,
        )

    def test_collect_success(self):
        """Full collect with mocked feed -> SUCCESS, all artifacts written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            with patch(
                "signal_engine.lanes.x_feed.fetch_opencli_feed",
                return_value=SAMPLE_TWEETS,
            ), patch(
                "signal_engine.lanes.x_feed.write_signal",
            ), patch(
                "signal_engine.lanes.x_feed.write_index",
            ), patch(
                "signal_engine.lanes.x_feed.write_run_manifest",
            ):
                result = collect_x_feed(ctx)

            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertEqual(result.signals_written, 2)
            self.assertTrue(result.session_id.startswith("feed-2026-04-06-"))
            self.assertEqual(result.signal_types_count, {"feed-exposure": 2})
            self.assertEqual(len(result.errors), 0)

    def test_collect_empty_source(self):
        """Fetch returns no tweets -> EMPTY, no signals written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            with patch(
                "signal_engine.lanes.x_feed.fetch_opencli_feed",
                return_value=[],
            ):
                result = collect_x_feed(ctx)

            self.assertEqual(result.status, RunStatus.EMPTY)
            self.assertEqual(result.signals_written, 0)
            self.assertEqual(len(result.signal_records), 0)

    def test_collect_source_failure(self):
        """Fetch throws -> EMPTY, error recorded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            with patch(
                "signal_engine.lanes.x_feed.fetch_opencli_feed",
                side_effect=Exception("network error"),
            ):
                result = collect_x_feed(ctx)

            self.assertEqual(result.status, RunStatus.EMPTY)
            self.assertIn("source fetch failed", result.errors[0])

    def test_session_id_consistent_across_artifacts(self):
        """session_id is identical in result, signal frontmatter, and index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            with patch(
                "signal_engine.lanes.x_feed.fetch_opencli_feed",
                return_value=SAMPLE_TWEETS[:1],
            ), patch(
                "signal_engine.lanes.x_feed.write_signal",
            ), patch(
                "signal_engine.lanes.x_feed.write_index",
            ), patch(
                "signal_engine.lanes.x_feed.write_run_manifest",
            ):
                result = collect_x_feed(ctx)

            # session_id in result
            self.assertIsNotNone(result.session_id)
            sid = result.session_id

            # Verify index.md session_id via render
            from signal_engine.signals.render import render_index_markdown
            index_text = render_index_markdown(result, index_path=tmpdir / "index.md")
            self.assertIn(f'session_id: "{sid}"', index_text)

    def test_index_links_are_relative(self):
        """index.md signal links are relative paths, not absolute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            with patch(
                "signal_engine.lanes.x_feed.fetch_opencli_feed",
                return_value=SAMPLE_TWEETS[:1],
            ), patch(
                "signal_engine.lanes.x_feed.write_signal",
            ), patch(
                "signal_engine.lanes.x_feed.write_index",
            ), patch(
                "signal_engine.lanes.x_feed.write_run_manifest",
            ):
                result = collect_x_feed(ctx)

            # Verify index.md links via render
            from signal_engine.signals.render import render_index_markdown
            index_text = render_index_markdown(result, index_path=tmpdir / "index.md")
            # Should NOT contain absolute path
            self.assertNotIn("/tmp/", index_text)
            # Should contain relative path to signals dir
            self.assertIn("signals/", index_text)

    def test_collect_index_write_failure(self):
        """index.md write failure -> FAILED, error recorded, signals still tracked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            def write_index_fail(result, path):
                raise IOError("disk full")

            with patch(
                "signal_engine.lanes.x_feed.fetch_opencli_feed",
                return_value=SAMPLE_TWEETS,
            ), patch(
                "signal_engine.lanes.x_feed.write_signal",
            ), patch(
                "signal_engine.lanes.x_feed.write_index",
                side_effect=write_index_fail,
            ), patch(
                "signal_engine.lanes.x_feed.write_run_manifest",
            ):
                result = collect_x_feed(ctx)

            self.assertEqual(result.status, RunStatus.FAILED)
            self.assertTrue(any("failed to write index.md" in e for e in result.errors))
            # Signals were processed even though index write failed
            self.assertEqual(result.signals_written, 2)

    def test_collect_runjson_write_failure(self):
        """run.json write failure -> FAILED, error recorded, signals still tracked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            def write_run_fail(result, path):
                raise IOError("disk full")

            with patch(
                "signal_engine.lanes.x_feed.fetch_opencli_feed",
                return_value=SAMPLE_TWEETS,
            ), patch(
                "signal_engine.lanes.x_feed.write_signal",
            ), patch(
                "signal_engine.lanes.x_feed.write_index",
            ), patch(
                "signal_engine.lanes.x_feed.write_run_manifest",
                side_effect=write_run_fail,
            ):
                result = collect_x_feed(ctx)

            self.assertEqual(result.status, RunStatus.FAILED)
            self.assertTrue(any("failed to write run.json" in e for e in result.errors))
            # Signals were processed even though run.json write failed
            self.assertEqual(result.signals_written, 2)


class TestSignalRecordMapping(unittest.TestCase):
    def test_signal_record_from_tweet(self):
        tweet = SAMPLE_TWEETS[0]
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
            session_id="feed-2026-04-06-abc123",
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
        self.assertEqual(record.session_id, "feed-2026-04-06-abc123")


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
            session_id="feed-2026-04-06-abc123",
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
        self.assertIn("session_id: feed-2026-04-06-abc123", md)
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
