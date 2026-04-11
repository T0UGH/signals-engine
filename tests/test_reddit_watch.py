"""Tests for reddit-watch lane and Reddit public source."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signals_engine.core import RunContext, RunStatus


class TestRedditWatchLane(unittest.TestCase):
    def _make_ctx(self, tmp_dir: str, lane_config: dict) -> RunContext:
        ctx = RunContext(
            lane="reddit-watch",
            date="2026-04-11",
            data_dir=Path(tmp_dir),
            config={"lanes": {"reddit-watch": lane_config}},
        )
        ctx.ensure_dirs()
        return ctx

    def test_collect_fails_when_queries_missing(self):
        from signals_engine.lanes.reddit_watch import collect_reddit_watch

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, {"lookback_days": 30, "max_threads": 5})
            result = collect_reddit_watch(ctx)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(result.signals_written, 0)
        self.assertTrue(any("queries" in err.lower() for err in result.errors))

    @patch("signals_engine.lanes.reddit_watch.fetch_reddit_threads")
    def test_collect_writes_signals_for_matching_threads(self, mock_fetch):
        from signals_engine.lanes.reddit_watch import collect_reddit_watch
        from signals_engine.sources.reddit_public import RedditThread

        mock_fetch.return_value = [
            RedditThread(
                thread_id="abc123",
                title="Three-agent Claude workflow that actually works",
                subreddit="ClaudeAI",
                author="devon",
                score=438,
                num_comments=149,
                created_at="2026-04-02T10:00:00Z",
                url="https://www.reddit.com/r/ClaudeAI/comments/abc123/three_agent_workflow/",
                permalink="/r/ClaudeAI/comments/abc123/three_agent_workflow/",
                body="I replaced solo coding with architect, builder, reviewer and token usage dropped a lot.",
                top_comments=[
                    "This matches what worked for our team too.",
                    "Reviewer role catches a lot of silent mistakes.",
                ],
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                {
                    "queries": ["AI coding agents"],
                    "lookback_days": 30,
                    "max_threads": 5,
                    "max_per_query": 3,
                },
            )
            result = collect_reddit_watch(ctx)
            record = result.signal_records[0]
            self.assertTrue(Path(record.file_path).exists())
            body = Path(record.file_path).read_text(encoding="utf-8")

            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertEqual(result.repos_checked, 1)
            self.assertEqual(result.signals_written, 1)
            self.assertEqual(record.lane, "reddit-watch")
            self.assertEqual(record.source, "reddit")
            self.assertEqual(record.signal_type, "reddit_thread")
            self.assertEqual(record.entity_id, "abc123")
            self.assertEqual(record.group, "r/ClaudeAI")
            self.assertEqual(record.likes, 438)
            self.assertEqual(record.replies, 149)
            self.assertIn("architect, builder, reviewer", record.text_preview)
            self.assertIn("## Post", body)
            self.assertIn("## Top Comments", body)
            self.assertIn("Reviewer role catches a lot of silent mistakes.", body)

    @patch("signals_engine.lanes.reddit_watch.fetch_reddit_threads")
    def test_collect_dedupes_same_thread_across_queries(self, mock_fetch):
        from signals_engine.lanes.reddit_watch import collect_reddit_watch
        from signals_engine.sources.reddit_public import RedditThread

        thread = RedditThread(
            thread_id="dup123",
            title="Shared thread",
            subreddit="artificial",
            author="alice",
            score=100,
            num_comments=20,
            created_at="2026-04-01T00:00:00Z",
            url="https://www.reddit.com/r/artificial/comments/dup123/shared_thread/",
            permalink="/r/artificial/comments/dup123/shared_thread/",
            body="Same thread returned for multiple queries.",
            top_comments=[],
        )
        mock_fetch.side_effect = [[thread], [thread]]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                {
                    "queries": ["AI coding agents", "Claude Code workflows"],
                    "lookback_days": 30,
                    "max_threads": 5,
                    "max_per_query": 3,
                },
            )
            result = collect_reddit_watch(ctx)

        self.assertEqual(result.status, RunStatus.SUCCESS)
        self.assertEqual(result.repos_checked, 2)
        self.assertEqual(result.signals_written, 1)


if __name__ == "__main__":
    unittest.main()
