"""Tests for rize-watch lane and source."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signals_engine.core import RunContext, RunStatus
from signals_engine.runtime.collect import collect_lane
from signals_engine.sources.rize import parse_ai_tools, RizeTool
from signals_engine.lanes.rize_watch import collect_rize_watch

HTML = """<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"ItemList","name":"Trending AI tools this week","itemListElement":[{"@type":"ListItem","position":2,"url":"https://github.com/acme/second","name":"second","description":"Second item"},{"@type":"ListItem","position":1,"url":"https://github.com/acme/first","name":"first","description":"First item"}]}</script></html>"""

class TestRizeSource(unittest.TestCase):
    def test_parse_itemlist(self):
        tools = parse_ai_tools(HTML)
        self.assertEqual([tool.name for tool in tools], ["first", "second"])
        self.assertEqual(tools[0].repo_slug, "acme/first")

    def test_missing_itemlist_fails_cleanly(self):
        with self.assertRaises(Exception):
            parse_ai_tools("<html></html>")

class TestRizeWatchLane(unittest.TestCase):
    def _ctx(self, tmp, max_items=1):
        return RunContext(lane="rize-watch", date="2026-05-16", config={"lanes": {"rize-watch": {"max_items": max_items}}}, data_dir=Path(tmp))

    @patch("signals_engine.lanes.rize_watch.fetch_ai_tools")
    def test_collect_writes_limited_signals(self, fetch):
        fetch.return_value = [RizeTool(1, "first", "https://github.com/acme/first", "First item"), RizeTool(2, "second", "https://github.com/acme/second", "Second item")]
        with tempfile.TemporaryDirectory() as td:
            result = collect_rize_watch(self._ctx(td, max_items=1))
            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertEqual(result.signals_written, 1)
            self.assertEqual(result.signal_records[0].entity_id, "acme/first")

    @patch("signals_engine.lanes.rize_watch.fetch_ai_tools")
    def test_runtime_collect_imports_registered_lane(self, fetch):
        fetch.return_value = [RizeTool(1, "first", "https://github.com/acme/first", "First item")]
        with tempfile.TemporaryDirectory() as td:
            result = collect_lane(self._ctx(td))
            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertEqual(result.signals_written, 1)
