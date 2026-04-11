"""Tests for reddit-watch lane and Reddit public source."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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
                external_url="https://blog.example.com/three-agent-workflow",
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
            self.assertEqual(
                record.source_url,
                "https://www.reddit.com/r/ClaudeAI/comments/abc123/three_agent_workflow/",
            )
            self.assertEqual(record.external_url, "https://blog.example.com/three-agent-workflow")
            self.assertIn("architect, builder, reviewer", record.text_preview)
            self.assertIn("## Post", body)
            self.assertIn("## Top Comments", body)
            self.assertIn("Reviewer role catches a lot of silent mistakes.", body)
            self.assertIn("External link: https://blog.example.com/three-agent-workflow", body)

    @patch("signals_engine.lanes.reddit_watch.fetch_reddit_threads")
    def test_collect_dedupes_same_thread_across_queries(self, mock_fetch):
        from signals_engine.lanes.reddit_watch import collect_reddit_watch
        from signals_engine.sources.reddit_public import RedditThread

        thread = RedditThread(
            thread_id="dup123",
            title="Shared Claude Code thread",
            subreddit="artificial",
            author="alice",
            score=100,
            num_comments=20,
            created_at="2026-04-01T00:00:00Z",
            url="https://www.reddit.com/r/artificial/comments/dup123/shared_thread/",
            permalink="/r/artificial/comments/dup123/shared_thread/",
            external_url="",
            body="Same thread returned for multiple AI coding queries.",
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

    @patch("signals_engine.lanes.reddit_watch.fetch_reddit_threads")
    def test_collect_rejects_invalid_integer_config(self, mock_fetch):
        from signals_engine.lanes.reddit_watch import collect_reddit_watch

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                {
                    "queries": ["AI coding agents"],
                    "lookback_days": 30,
                    "max_threads": 5,
                    "max_per_query": 0,
                },
            )
            result = collect_reddit_watch(ctx)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(result.signals_written, 0)
        self.assertTrue(any("max_per_query" in err for err in result.errors))
        mock_fetch.assert_not_called()

    @patch("signals_engine.lanes.reddit_watch.fetch_reddit_threads")
    def test_collect_filters_out_generic_non_ai_news(self, mock_fetch):
        from signals_engine.lanes.reddit_watch import collect_reddit_watch
        from signals_engine.sources.reddit_public import RedditThread

        mock_fetch.return_value = [
            RedditThread(
                thread_id="generic1",
                title="Startup founder raises $20M after conference launch",
                subreddit="technology",
                author="newsbot",
                score=800,
                num_comments=250,
                created_at="2026-04-10T00:00:00Z",
                url="https://www.reddit.com/r/technology/comments/generic1/startup_founder_raises_20m/",
                permalink="/r/technology/comments/generic1/startup_founder_raises_20m/",
                external_url="https://news.example.com/funding",
                body="This is a generic startup funding story about hiring, marketing, and conference buzz.",
                top_comments=["Big week for founders and VCs."],
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

        self.assertEqual(result.status, RunStatus.EMPTY)
        self.assertEqual(result.signals_written, 0)

    def test_collect_lane_registers_reddit_watch_without_direct_module_import(self):
        from signals_engine.runtime.collect import collect_lane
        from signals_engine.lanes.registry import LANE_REGISTRY

        previous_module = sys.modules.pop("signals_engine.lanes.reddit_watch", None)
        previous_collector = LANE_REGISTRY["reddit-watch"]
        LANE_REGISTRY["reddit-watch"] = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_ctx(tmp, {"lookback_days": 30, "max_threads": 5})
                result = collect_lane(ctx)
            self.assertEqual(result.status, RunStatus.FAILED)
            self.assertTrue(any("queries" in err.lower() for err in result.errors))
            self.assertIsNotNone(LANE_REGISTRY["reddit-watch"])
        finally:
            if previous_module is not None:
                sys.modules["signals_engine.lanes.reddit_watch"] = previous_module
            LANE_REGISTRY["reddit-watch"] = previous_collector

    def test_lanes_list_includes_reddit_watch(self):
        from signals_engine.commands import lanes

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = lanes.run(type("Args", (), {"subcommand": "list"})())

        self.assertEqual(rc, 0)
        self.assertIn("reddit-watch", buf.getvalue().splitlines())


class TestRedditPublicSource(unittest.TestCase):
    def test_normalize_subreddit_name_only_removes_explicit_prefix(self):
        from signals_engine.sources.reddit_public import _normalize_subreddit_name

        self.assertEqual(_normalize_subreddit_name("redditdev"), "redditdev")
        self.assertEqual(_normalize_subreddit_name(" r/ClaudeAI "), "ClaudeAI")
        self.assertEqual(_normalize_subreddit_name("   "), "")

    def test_search_time_window_maps_to_supported_reddit_ranges(self):
        from signals_engine.sources.reddit_public import _search_time_window

        self.assertEqual(_search_time_window(1), "day")
        self.assertEqual(_search_time_window(7), "week")
        self.assertEqual(_search_time_window(30), "month")
        self.assertEqual(_search_time_window(90), "year")
        self.assertEqual(_search_time_window(500), "all")

    @patch("signals_engine.sources.reddit_public._extract_top_comments", return_value=["use reviewer agents"])
    @patch("signals_engine.sources.reddit_public._request_json")
    def test_fetch_reddit_threads_uses_normalized_subreddit_and_time_window(self, mock_request_json, _mock_comments):
        from signals_engine.sources.reddit_public import fetch_reddit_threads

        mock_request_json.return_value = {"data": {"children": []}}
        fetch_reddit_threads(
            "Claude Code",
            lookback_days=90,
            max_threads=2,
            subreddits=["redditdev", "r/ClaudeAI", "   "],
        )

        called_urls = [call.args[0] for call in mock_request_json.call_args_list]
        self.assertEqual(len(called_urls), 2)
        self.assertIn("/r/redditdev/search.json", called_urls[0])
        self.assertIn("/r/ClaudeAI/search.json", called_urls[1])
        self.assertIn("t=year", called_urls[0])
        self.assertIn("t=year", called_urls[1])

    @patch("signals_engine.sources.reddit_public._extract_top_comments", return_value=["top comment"])
    @patch("signals_engine.sources.reddit_public._request_json")
    def test_fetch_reddit_threads_prefers_reddit_permalink_for_link_posts(self, mock_request_json, _mock_comments):
        from signals_engine.sources.reddit_public import fetch_reddit_threads

        mock_request_json.return_value = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "abc123",
                            "title": "Claude Code writeup",
                            "subreddit": "ClaudeAI",
                            "author": "devon",
                            "score": 10,
                            "num_comments": 3,
                            "created_utc": 1775000000,
                            "permalink": "/r/ClaudeAI/comments/abc123/claude_code_writeup/",
                            "url": "https://blog.example.com/claude-code-writeup",
                            "selftext": "",
                        }
                    }
                ]
            }
        }

        threads = fetch_reddit_threads("Claude Code", lookback_days=30, max_threads=5)

        self.assertEqual(len(threads), 1)
        self.assertEqual(
            threads[0].url,
            "https://www.reddit.com/r/ClaudeAI/comments/abc123/claude_code_writeup/",
        )
        self.assertEqual(threads[0].external_url, "https://blog.example.com/claude-code-writeup")


if __name__ == "__main__":
    unittest.main()
