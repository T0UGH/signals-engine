"""Tests for hacker-news-search-watch lane and Hacker News search source."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from signals_engine.core import RunContext, RunStatus


class TestHackerNewsSearchWatchLane(unittest.TestCase):
    def _make_ctx(self, tmp_dir: str, lane_config: dict) -> RunContext:
        ctx = RunContext(
            lane="hacker-news-search-watch",
            date="2026-04-18",
            data_dir=Path(tmp_dir),
            config={"lanes": {"hacker-news-search-watch": lane_config}},
        )
        ctx.ensure_dirs()
        return ctx

    @patch("signals_engine.lanes.hacker_news_search_watch.fetch_hackernews_search_stories")
    def test_collect_fails_when_queries_missing(self, mock_fetch):
        from signals_engine.lanes.hacker_news_search_watch import collect_hacker_news_search_watch

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, {"max_hits_per_query": 5})
            result = collect_hacker_news_search_watch(ctx)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(result.signals_written, 0)
        self.assertTrue(any("queries" in err.lower() for err in result.errors))
        mock_fetch.assert_not_called()

    @patch("signals_engine.lanes.hacker_news_search_watch.fetch_hackernews_search_stories")
    def test_collect_uses_defaults_when_optional_config_missing(self, mock_fetch):
        from signals_engine.lanes.hacker_news_search_watch import collect_hacker_news_search_watch

        mock_fetch.return_value = []

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, {"queries": ["agent workflow"]})
            result = collect_hacker_news_search_watch(ctx)

        self.assertEqual(result.status, RunStatus.EMPTY)
        mock_fetch.assert_called_once_with(
            queries=["agent workflow"],
            max_hits_per_query=5,
            fetch_top_comments=True,
            max_top_comments=3,
        )

    @patch("signals_engine.lanes.hacker_news_search_watch.fetch_hackernews_search_stories")
    def test_collect_writes_deduped_story_signals_with_query_context(self, mock_fetch):
        from signals_engine.lanes.hacker_news_search_watch import collect_hacker_news_search_watch
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
                story_list_name="search:story",
                top_comments=[
                    "This is the first useful benchmark I have seen.",
                    "The comments have already stripped HTML entities & tags.",
                ],
                query="agent workflow",
            ),
            HackerNewsStory(
                story_id=45678902,
                title="A second HN story",
                discussion_url="https://news.ycombinator.com/item?id=45678902",
                external_url="",
                author="pg",
                created_at="2026-04-18T11:00:00Z",
                score=300,
                descendants=45,
                position=2,
                text_preview="A second cleaned story preview.",
                story_list_name="search:story",
                top_comments=[],
                query="hn search",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                {
                    "queries": ["agent workflow", "hn search"],
                    "max_hits_per_query": 5,
                    "fetch_top_comments": True,
                    "max_top_comments": 2,
                },
            )
            result = collect_hacker_news_search_watch(ctx)

            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertEqual(result.signals_written, 2)
            self.assertEqual(result.repos_checked, 2)

            record = result.signal_records[0]
            self.assertTrue(Path(record.file_path).exists())
            body = Path(record.file_path).read_text(encoding="utf-8")

        self.assertEqual(record.lane, "hacker-news-search-watch")
        self.assertEqual(record.signal_type, "hackernews_story_search_hit")
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
        self.assertEqual(record.group, "search:story")
        self.assertEqual(record.query, "agent workflow")
        self.assertEqual(record.text_preview, "A cleaned summary of the benchmark write-up.")
        self.assertIn("query: agent workflow", body)
        self.assertIn("group: search:story", body)
        self.assertIn("## Story", body)
        self.assertIn("## Top Comments", body)
        self.assertIn("Matched query: agent workflow", body)
        self.assertIn("Discussion URL: https://news.ycombinator.com/item?id=45678901", body)
        self.assertIn("External article: https://example.com/benchmark", body)
        self.assertIn("The comments have already stripped HTML entities & tags.", body)

    def test_collect_lane_registers_hacker_news_search_watch_without_direct_module_import(self):
        from signals_engine.lanes.registry import LANE_REGISTRY
        from signals_engine.runtime.collect import collect_lane

        previous_module = sys.modules.pop("signals_engine.lanes.hacker_news_search_watch", None)
        previous_collector = LANE_REGISTRY["hacker-news-search-watch"]
        LANE_REGISTRY["hacker-news-search-watch"] = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_ctx(tmp, {"max_hits_per_query": 5})
                result = collect_lane(ctx)
            self.assertEqual(result.status, RunStatus.FAILED)
            self.assertTrue(any("queries" in err.lower() for err in result.errors))
            self.assertIsNotNone(LANE_REGISTRY["hacker-news-search-watch"])
        finally:
            if previous_module is not None:
                sys.modules["signals_engine.lanes.hacker_news_search_watch"] = previous_module
            LANE_REGISTRY["hacker-news-search-watch"] = previous_collector

    def test_lanes_list_includes_hacker_news_search_watch(self):
        from signals_engine.commands import lanes

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = lanes.run(type("Args", (), {"subcommand": "list"})())

        self.assertEqual(rc, 0)
        self.assertIn("hacker-news-search-watch", buf.getvalue().splitlines())


class TestHackerNewsSearchSource(unittest.TestCase):
    @patch("signals_engine.sources.hackernews._fetch_top_level_comments")
    @patch("signals_engine.sources.hackernews._request_json")
    def test_fetch_hackernews_search_stories_filters_to_story_hits_and_valid_story_ids(
        self,
        mock_request_json,
        mock_fetch_comments,
    ):
        from signals_engine.sources.hackernews import fetch_hackernews_search_stories

        mock_fetch_comments.side_effect = [
            ["top-level comment for 101"],
            ["top-level comment for 202"],
            [],
        ]

        def fake_request_json(url: str, *, timeout: int):
            parsed = urlparse(url)
            if "hn.algolia.com" in parsed.netloc:
                query = parse_qs(parsed.query)["query"][0]
                if query == "agent workflow":
                    return {
                        "hits": [
                            {"objectID": "101", "_tags": ["story", "author_dang"]},
                            {"objectID": "bad-id", "_tags": ["story"]},
                            {"objectID": "991", "story_id": 991, "_tags": ["comment", "story_991"]},
                            {"objectID": "202", "_tags": ["story"]},
                        ]
                    }
                if query == "hn search":
                    return {
                        "hits": [
                            {"objectID": "202", "_tags": ["story"]},
                            {"objectID": "ignored", "story_id": 303, "_tags": ["story"]},
                        ]
                    }
                raise AssertionError(f"unexpected query URL: {url}")

            if url.endswith("/item/101.json"):
                return {
                    "id": 101,
                    "type": "story",
                    "title": "Canonical 101 title",
                    "url": "https://example.com/101",
                    "by": "dang",
                    "time": 1776506400,
                    "score": 500,
                    "descendants": 80,
                    "text": "<p>Canonical <b>story</b> text.</p>",
                    "kids": [1001],
                }
            if url.endswith("/item/202.json"):
                return {
                    "id": 202,
                    "type": "story",
                    "title": "Canonical 202 title",
                    "url": "",
                    "by": "pg",
                    "time": 1776510000,
                    "score": 320,
                    "descendants": 12,
                    "text": "",
                    "kids": [2001],
                }
            if url.endswith("/item/303.json"):
                return {
                    "id": 303,
                    "type": "story",
                    "title": "Canonical 303 title",
                    "url": "https://example.com/303",
                    "by": "sama",
                    "time": 1776513600,
                    "score": 250,
                    "descendants": 30,
                    "text": "<div>Third story body</div>",
                    "kids": [],
                }
            raise AssertionError(f"unexpected URL: {url}")

        mock_request_json.side_effect = fake_request_json

        stories = fetch_hackernews_search_stories(
            queries=["agent workflow", "hn search"],
            max_hits_per_query=5,
            fetch_top_comments=True,
            max_top_comments=1,
        )

        self.assertEqual([story.story_id for story in stories], [101, 202, 303])
        self.assertEqual([story.query for story in stories], ["agent workflow", "agent workflow", "hn search"])
        self.assertEqual([story.story_list_name for story in stories], ["search:story", "search:story", "search:story"])
        self.assertEqual(stories[0].title, "Canonical 101 title")
        self.assertEqual(stories[0].external_url, "https://example.com/101")
        self.assertEqual(stories[0].text_preview, "Canonical story text.")
        self.assertEqual(stories[0].top_comments, ["top-level comment for 101"])
        self.assertEqual(stories[1].text_preview, "Canonical 202 title")
        self.assertEqual(stories[1].discussion_url, "https://news.ycombinator.com/item?id=202")
        self.assertEqual(stories[2].top_comments, [])


if __name__ == "__main__":
    unittest.main()
