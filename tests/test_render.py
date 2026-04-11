"""Tests for the render chain: signal markdown, index.md, run.json."""
import unittest
import sys
import os
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signals_engine.core import RunResult, RunStatus, SignalRecord
from signals_engine.signals.render import render_signal_markdown, render_index_markdown
from signals_engine.signals.frontmatter import build_frontmatter
from signals_engine.runtime.run_manifest import render_run_manifest


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

    def test_build_frontmatter_github_release_by_source_and_type(self):
        record = SignalRecord(
            lane="claude-code-watch",
            signal_type="release",
            source="github",
            entity_type="repo",
            entity_id="anthropics/claude-code",
            title="v1.2.3",
            source_url="https://github.com/anthropics/claude-code/releases/tag/v1.2.3",
            fetched_at="2026-04-11T10:00:00Z",
            file_path="/tmp/test.md",
            handle="anthropics/claude-code",
            post_id="v1.2.3",
            created_at="2026-04-11T09:00:00Z",
            prerelease=True,
        )

        fm = build_frontmatter(record)

        self.assertIn("lane: claude-code-watch", fm)
        self.assertIn("source: github", fm)
        self.assertIn("version: v1.2.3", fm)
        self.assertIn("published_at: '2026-04-11T09:00:00Z'", fm)
        self.assertIn("prerelease: true", fm)


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

    def test_render_signal_markdown_github_release_by_source_and_type(self):
        record = SignalRecord(
            lane="codex-watch",
            signal_type="release",
            source="github",
            entity_type="repo",
            entity_id="openai/codex",
            title="v0.9.0",
            source_url="https://github.com/openai/codex/releases/tag/v0.9.0",
            fetched_at="2026-04-11T11:00:00Z",
            file_path="/tmp/signals/codex-watch/001.md",
            handle="openai/codex",
            post_id="v0.9.0",
            created_at="2026-04-11T10:00:00Z",
            release_body="Release notes here",
            release_assets=[
                {
                    "name": "codex-macos.dmg",
                    "browser_download_url": "https://example.com/codex-macos.dmg",
                    "size_mb": 42.5,
                }
            ],
        )

        md = render_signal_markdown(record)

        self.assertIn("## Release Notes", md)
        self.assertIn("Release notes here", md)
        self.assertIn("## Assets", md)
        self.assertIn("codex-macos.dmg", md)

    def test_render_signal_markdown_github_changelog_by_source_and_type(self):
        record = SignalRecord(
            lane="openclaw-watch",
            signal_type="changelog",
            source="github",
            entity_type="repo",
            entity_id="openclaw/openclaw",
            title="openclaw CHANGELOG updated",
            source_url="https://github.com/openclaw/openclaw/blob/HEAD/CHANGELOG.md",
            fetched_at="2026-04-11T12:00:00Z",
            file_path="/tmp/signals/openclaw-watch/001.md",
            handle="openclaw/openclaw",
            post_id="CHANGELOG.md",
            diff_stats="+3 lines, -1 lines",
            diff_text="+ added\n- removed",
        )

        md = render_signal_markdown(record)

        self.assertIn("## Change Summary", md)
        self.assertIn("+3 lines, -1 lines", md)
        self.assertIn("```diff", md)
        self.assertIn("+ added", md)

    def test_render_signal_markdown_github_merged_pr(self):
        record = SignalRecord(
            lane="codex-watch",
            signal_type="merged_pr",
            source="github",
            entity_type="repo",
            entity_id="openai/codex",
            title="Add better non-interactive review mode",
            source_url="https://github.com/openai/codex/pull/321",
            fetched_at="2026-04-11T12:30:00Z",
            file_path="/tmp/signals/codex-watch/merged-pr.md",
            handle="alice",
            post_id="321",
            created_at="2026-04-11T09:00:00Z",
            text_preview="Implements a better review mode for automation.",
            likes=321,
            replies=0,
            views=0,
        )

        md = render_signal_markdown(record)

        self.assertIn("Merged PR #321", md)
        self.assertIn("Add better non-interactive review mode", md)
        self.assertIn("Implements a better review mode", md)
        self.assertIn("alice", md)

    def test_render_signal_markdown_github_commit(self):
        record = SignalRecord(
            lane="codex-watch",
            signal_type="commit",
            source="github",
            entity_type="repo",
            entity_id="openai/codex",
            title="Improve agent resume behavior",
            source_url="https://github.com/openai/codex/commit/1234567890abcdef",
            fetched_at="2026-04-11T12:45:00Z",
            file_path="/tmp/signals/codex-watch/commit.md",
            handle="bob",
            post_id="1234567890abcdef",
            created_at="2026-04-11T10:00:00Z",
            text_preview="Improve agent resume behavior",
        )

        md = render_signal_markdown(record)

        self.assertIn("Commit 1234567", md)
        self.assertIn("Improve agent resume behavior", md)
        self.assertIn("bob", md)


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
