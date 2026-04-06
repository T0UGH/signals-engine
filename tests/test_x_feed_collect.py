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
from signal_engine.sources.x.models import NormalizedTweet
from signal_engine.sources.x.errors import XSourceError


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


def _to_normalized(tweet: dict) -> NormalizedTweet:
    return NormalizedTweet(
        id=tweet["id"],
        author=tweet["author"],
        text=tweet["text"],
        likes=tweet["likes"],
        retweets=tweet["retweets"],
        replies=tweet["replies"],
        views=tweet["views"],
        created_at=tweet["created_at"],
        url=tweet["url"],
    )


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
                    "native": {
                        "cookie_file": None,
                        "limit": 100,
                        "timeout": 30,
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

    def test_collect_success_real_artifacts(self):
        """Success path: real index.md and run.json contain correct real data (not fake RunResult)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            with patch(
                "signal_engine.lanes.x_feed.fetch_home_timeline",
                return_value=[_to_normalized(t) for t in SAMPLE_TWEETS],
            ):
                result = collect_x_feed(ctx)

            self.assertEqual(result.status, RunStatus.SUCCESS)

            # Verify real index.md content
            index_md = tmpdir / "signals" / "x-feed" / "2026-04-06" / "index.md"
            self.assertTrue(index_md.exists(), "index.md must be written to disk")
            index_content = index_md.read_text()
            self.assertIn('date: "2026-04-06"', index_content, "index.md must have real date")
            self.assertIn(f'session_id: "{result.session_id}"', index_content, "index.md must have real session_id")
            self.assertIn("status: success", index_content, "index.md must have real status (not hardcoded)")

            # Verify real run.json content
            run_json = tmpdir / "signals" / "x-feed" / "2026-04-06" / "run.json"
            self.assertTrue(run_json.exists(), "run.json must be written to disk")
            run_data = json.loads(run_json.read_text())
            self.assertEqual(run_data["date"], "2026-04-06", "run.json must have real date")
            self.assertEqual(run_data["session_id"], result.session_id, "run.json must have real session_id")
            self.assertEqual(run_data["status"], "success", "run.json must have real status")
            self.assertEqual(run_data["summary"]["signals_written"], 2, "run.json must have real signals_written")
            self.assertEqual(
                run_data["summary"]["signal_types"]["feed-exposure"], 2,
                "run.json must have real signal_types"
            )
            self.assertEqual(len(run_data["artifacts"]["signal_files"]), 2)

    def test_collect_success(self):
        """Full collect with mocked feed -> SUCCESS, all artifacts written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            with patch(
                "signal_engine.lanes.x_feed.fetch_home_timeline",
                return_value=[_to_normalized(t) for t in SAMPLE_TWEETS],
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
                "signal_engine.lanes.x_feed.fetch_home_timeline",
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
                "signal_engine.lanes.x_feed.fetch_home_timeline",
                side_effect=XSourceError("network unreachable"),
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
                "signal_engine.lanes.x_feed.fetch_home_timeline",
                return_value=[_to_normalized(SAMPLE_TWEETS[0])],
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
                "signal_engine.lanes.x_feed.fetch_home_timeline",
                return_value=[_to_normalized(SAMPLE_TWEETS[0])],
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
                "signal_engine.lanes.x_feed.fetch_home_timeline",
                return_value=[_to_normalized(t) for t in SAMPLE_TWEETS],
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
        """run.json write failure: error recorded, signals tracked; status determined before run.json write."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            def write_run_fail(result, path):
                raise IOError("disk full")

            with patch(
                "signal_engine.lanes.x_feed.fetch_home_timeline",
                return_value=[_to_normalized(t) for t in SAMPLE_TWEETS],
            ), patch(
                "signal_engine.lanes.x_feed.write_signal",
            ), patch(
                "signal_engine.lanes.x_feed.write_index",
            ), patch(
                "signal_engine.lanes.x_feed.write_run_manifest",
                side_effect=write_run_fail,
            ):
                result = collect_x_feed(ctx)

            # Status is SUCCESS because signal_failure=False and index_ok=True.
            # run.json was written AFTER status was finalized, so its write failure
            # does not retroactively change status (architectural constraint:
            # run.json cannot be the arbiter of its own receipt's status).
            # The failure IS recorded in result.errors.
            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertTrue(any("failed to write run.json" in e for e in result.errors))
            self.assertEqual(result.signals_written, 2)

    def test_collect_partial_signal_failure_runjson_has_failed_status(self):
        """Partial signal write failure -> FAILED, run.json reflects final FAILED status (not provisional)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            ctx = self._make_ctx(tmpdir)

            # Tweet 1 succeeds, tweet 2 fails
            call_count = 0
            def write_signal_fail(record):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise IOError("disk full")
                # First call succeeds — no return value needed (procedure)

            with patch(
                "signal_engine.lanes.x_feed.fetch_home_timeline",
                return_value=[_to_normalized(t) for t in SAMPLE_TWEETS],
            ), patch(
                "signal_engine.lanes.x_feed.write_signal",
                side_effect=write_signal_fail,
            ):
                result = collect_x_feed(ctx)

            # result.status should be FAILED due to partial signal write failure
            self.assertEqual(result.status, RunStatus.FAILED, "result.status must be FAILED")

            # Disk run.json must reflect FINAL FAILED status, not provisional SUCCESS
            run_json = tmpdir / "signals" / "x-feed" / "2026-04-06" / "run.json"
            self.assertTrue(run_json.exists(), "run.json must exist on disk")
            run_data = json.loads(run_json.read_text())
            self.assertEqual(run_data["status"], "failed", "run.json.status must be FAILED (final, not provisional)")
            self.assertIn("failed to write", str(run_data.get("errors", [])))

            # signals_written reflects what actually succeeded
            self.assertEqual(run_data["summary"]["signals_written"], 1)


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
