"""Tests for the render chain: signal markdown, index.md, run.json."""
import unittest
import sys
import os
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signal_engine.core import RunResult, RunStatus, SignalRecord
from signal_engine.signals.render import render_signal_markdown, render_index_markdown
from signal_engine.signals.frontmatter import build_frontmatter
from signal_engine.runtime.run_manifest import render_run_manifest


class TestFrontmatter(unittest.TestCase):
    def test_build_frontmatter_x_feed(self):
        record = SignalRecord(
            lane="x-feed",
            signal_type="feed-exposure",
            source="x",
            entity_type="author",
            entity_id="elonmusk",
            title="@elonmusk #1",
            source_url="https://x.com/elonmusk/status/123",
            fetched_at="2026-04-06T10:00:00Z",
            file_path="/tmp/signals/x-feed/2026-04-06/001.md",
            handle="elonmusk",
            post_id="123",
            created_at="2026-04-06T09:00:00Z",
            position=1,
            text_preview="Hello world",
            likes=1000,
            retweets=200,
            replies=50,
            views=50000,
        )
        fm = build_frontmatter(record)
        self.assertIn("type: feed-exposure", fm)
        self.assertIn("source: x", fm)
        self.assertIn("handle: elonmusk", fm)

    def test_build_frontmatter_minimal(self):
        record = SignalRecord(
            lane="x-feed",
            signal_type="feed-exposure",
            source="x",
            entity_type="author",
            entity_id="testuser",
            title="@testuser #1",
            source_url="https://x.com/testuser/status/1",
            fetched_at="2026-04-06T10:00:00Z",
            file_path="/tmp/test.md",
        )
        fm = build_frontmatter(record)
        self.assertIn("type: feed-exposure", fm)
        self.assertIn("source: x", fm)


class TestSignalMarkdown(unittest.TestCase):
    def test_render_signal_markdown_x_feed(self):
        record = SignalRecord(
            lane="x-feed",
            signal_type="feed-exposure",
            source="x",
            entity_type="author",
            entity_id="sama",
            title="@sama #2",
            source_url="https://x.com/sama/status/456",
            fetched_at="2026-04-06T11:00:00Z",
            file_path="/tmp/signals/x-feed/2026-04-06/002.md",
            handle="sama",
            post_id="456",
            created_at="2026-04-06T10:30:00Z",
            position=2,
            text_preview="GM",
            likes=5000,
            retweets=800,
            replies=100,
            views=100000,
        )
        md = render_signal_markdown(record)
        lines = md.split("\n")
        self.assertEqual(lines[0], "---")
        self.assertIn("## Post", md)
        self.assertIn("GM", md)
        self.assertIn("## Engagement", md)
        self.assertIn("Likes: 5000", md)
        self.assertIn("Position in session: #2", md)


class TestRunManifest(unittest.TestCase):
    def test_render_run_manifest_basic(self):
        record = SignalRecord(
            lane="x-feed",
            signal_type="feed-exposure",
            source="x",
            entity_type="author",
            entity_id="test",
            title="@test #1",
            source_url="https://x.com/test/status/1",
            fetched_at="2026-04-06T10:00:00Z",
            file_path="/tmp/signal.md",
        )
        result = RunResult(
            lane="x-feed",
            date="2026-04-06",
            status=RunStatus.SUCCESS,
            started_at="2026-04-06T10:00:00Z",
            finished_at="2026-04-06T10:01:00Z",
            warnings=[],
            errors=[],
            signal_records=[record],
            repos_checked=1,
            signals_written=1,
            signal_types_count={"feed-exposure": 1},
            index_file="/tmp/index.md",
        )
        manifest = render_run_manifest(result)
        self.assertEqual(manifest["lane"], "x-feed")
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(manifest["summary"]["signals_written"], 1)
        self.assertIn("signal_files", manifest["artifacts"])
        self.assertEqual(manifest["artifacts"]["signal_files"], ["/tmp/signal.md"])

    def test_render_run_manifest_empty(self):
        result = RunResult(
            lane="x-feed",
            date="2026-04-06",
            status=RunStatus.EMPTY,
            started_at="2026-04-06T10:00:00Z",
            finished_at="",
            warnings=["no signals captured"],
            errors=[],
            signal_records=[],
            repos_checked=1,
            signals_written=0,
            signal_types_count={},
            index_file=None,
        )
        manifest = render_run_manifest(result)
        self.assertEqual(manifest["status"], "empty")
        self.assertEqual(manifest["summary"]["signals_written"], 0)
        self.assertEqual(manifest["artifacts"]["signal_files"], [])


class TestIndexMarkdown(unittest.TestCase):
    def test_render_index_markdown_with_signals(self):
        record = SignalRecord(
            lane="x-feed",
            signal_type="feed-exposure",
            source="x",
            entity_type="author",
            entity_id="sama",
            title="@sama",
            source_url="https://x.com/sama/status/1",
            fetched_at="2026-04-06T10:00:00Z",
            file_path="/tmp/signals/001.md",
            handle="sama",
        )
        result = RunResult(
            lane="x-feed",
            date="2026-04-06",
            status=RunStatus.SUCCESS,
            started_at="2026-04-06T10:00:00Z",
            finished_at="2026-04-06T10:01:00Z",
            warnings=[],
            errors=[],
            signal_records=[record],
            repos_checked=1,
            signals_written=1,
            signal_types_count={"feed-exposure": 1},
            index_file="/tmp/index.md",
        )
        md = render_index_markdown(result)
        self.assertIn("x-feed", md)
        self.assertIn("2026-04-06", md)
        self.assertIn("@sama", md)
        self.assertIn("feed-exposure", md)

    def test_render_index_markdown_empty(self):
        result = RunResult(
            lane="x-feed",
            date="2026-04-06",
            status=RunStatus.EMPTY,
            started_at="2026-04-06T10:00:00Z",
            finished_at="2026-04-06T10:01:00Z",
            warnings=[],
            errors=[],
            signal_records=[],
            repos_checked=1,
            signals_written=0,
            signal_types_count={},
            index_file=None,
        )
        md = render_index_markdown(result)
        self.assertIn("No signals captured", md)


if __name__ == "__main__":
    unittest.main()
