"""Tests for hacker-news-watch lane and Hacker News source."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from signals_engine.core import RunContext, RunStatus


class TestHackerNewsWatchLane(unittest.TestCase):
    def _make_ctx(self, tmp_dir: str, lane_config: dict) -> RunContext:
        ctx = RunContext(
            lane="hacker-news-watch",
            date="2026-04-18",
            data_dir=Path(tmp_dir),
            config={"lanes": {"hacker-news-watch": lane_config}},
        )
        ctx.ensure_dirs()
        return ctx

    @patch("signals_engine.lanes.hacker_news_watch.fetch_hackernews_stories")
    def test_collect_rejects_invalid_integer_config(self, mock_fetch):
        from signals_engine.lanes.hacker_news_watch import collect_hacker_news_watch

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, {"max_stories": 0})
            result = collect_hacker_news_watch(ctx)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(result.signals_written, 0)
        self.assertTrue(any("max_stories" in err for err in result.errors))
        mock_fetch.assert_not_called()

    @patch("signals_engine.lanes.hacker_news_watch.fetch_hackernews_stories")
    def test_collect_uses_defaults_when_config_missing(self, mock_fetch):
        from signals_engine.lanes.hacker_news_watch import collect_hacker_news_watch

        mock_fetch.return_value = []

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, {})
            result = collect_hacker_news_watch(ctx)

        self.assertEqual(result.status, RunStatus.EMPTY)
        mock_fetch.assert_called_once_with(
            story_list="top",
            max_stories=10,
            fetch_top_comments=True,
            max_top_comments=3,
        )

    @patch("signals_engine.lanes.hacker_news_watch.fetch_hackernews_stories")
    def test_collect_writes_story_signals_from_source_data(self, mock_fetch):
        from signals_engine.lanes.hacker_news_watch import collect_hacker_news_watch
        from signals_engine.sources.hackernews import HackerNewsStory

        mock_fetch.return_value = [
            HackerNewsStory(
                story_id=45678901,
                title="New terminal agent workflow benchmark",
                discussion_url="https://news.ycombinator.com/item?id=45678901",
                external_url="https://example.com/benchmark",
                author="dang",
                created_at="2026-04-18T10:00:00Z",
                score=512,
                descendants=87,
                position=1,
                text_preview="A cleaned summary of the benchmark write-up.",
                story_list_name="topstories",
                top_comments=[
                    "This is the first useful benchmark I have seen.",
                    "The comments have already stripped HTML entities & tags.",
                ],
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                {
                    "story_list": "top",
                    "max_stories": 1,
                    "fetch_top_comments": True,
                    "max_top_comments": 2,
                },
            )
            result = collect_hacker_news_watch(ctx)

            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertEqual(result.signals_written, 1)
            self.assertEqual(result.repos_checked, 1)

            record = result.signal_records[0]
            self.assertTrue(Path(record.file_path).exists())
            body = Path(record.file_path).read_text(encoding="utf-8")

        self.assertEqual(record.lane, "hacker-news-watch")
        self.assertEqual(record.signal_type, "hackernews_story")
        self.assertEqual(record.source, "hackernews")
        self.assertEqual(record.entity_type, "story")
        self.assertEqual(record.entity_id, "45678901")
        self.assertEqual(record.source_url, "https://news.ycombinator.com/item?id=45678901")
        self.assertEqual(record.external_url, "https://example.com/benchmark")
        self.assertEqual(record.handle, "dang")
        self.assertEqual(record.created_at, "2026-04-18T10:00:00Z")
        self.assertEqual(record.likes, 512)
        self.assertEqual(record.replies, 87)
        self.assertEqual(record.position, 1)
        self.assertEqual(record.group, "topstories")
        self.assertEqual(record.text_preview, "A cleaned summary of the benchmark write-up.")
        self.assertIn("## Story", body)
        self.assertIn("## Top Comments", body)
        self.assertIn("Discussion URL: https://news.ycombinator.com/item?id=45678901", body)
        self.assertIn("External article: https://example.com/benchmark", body)
        self.assertIn("The comments have already stripped HTML entities & tags.", body)

    def test_collect_lane_registers_hacker_news_watch_without_direct_module_import(self):
        from signals_engine.lanes.registry import LANE_REGISTRY
        from signals_engine.runtime.collect import collect_lane

        previous_module = sys.modules.pop("signals_engine.lanes.hacker_news_watch", None)
        previous_collector = LANE_REGISTRY["hacker-news-watch"]
        LANE_REGISTRY["hacker-news-watch"] = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_ctx(tmp, {"max_stories": 0})
                result = collect_lane(ctx)
            self.assertEqual(result.status, RunStatus.FAILED)
            self.assertTrue(any("max_stories" in err for err in result.errors))
            self.assertIsNotNone(LANE_REGISTRY["hacker-news-watch"])
        finally:
            if previous_module is not None:
                sys.modules["signals_engine.lanes.hacker_news_watch"] = previous_module
            LANE_REGISTRY["hacker-news-watch"] = previous_collector

    def test_lanes_list_includes_hacker_news_watch(self):
        from signals_engine.commands import lanes

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = lanes.run(type("Args", (), {"subcommand": "list"})())

        self.assertEqual(rc, 0)
        self.assertIn("hacker-news-watch", buf.getvalue().splitlines())


class TestHackerNewsSource(unittest.TestCase):
    def test_validate_story_list_rejects_unsupported_values(self):
        from signals_engine.sources.hackernews import validate_story_list

        with self.assertRaises(ValueError):
            validate_story_list("frontpage")

    def test_clean_html_text_strips_tags_and_entities(self):
        from signals_engine.sources.hackernews import clean_html_text

        cleaned = clean_html_text("<p>Hello &amp; <i>world</i>.</p><p>Line&nbsp;2<br>next</p>")

        self.assertEqual(cleaned, "Hello & world.\n\nLine 2\nnext")
        self.assertNotIn("<p>", cleaned)
        self.assertNotIn("&amp;", cleaned)
        self.assertNotIn("&nbsp;", cleaned)


if __name__ == "__main__":
    unittest.main()
