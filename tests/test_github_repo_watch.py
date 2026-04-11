"""Tests for GitHub repo-watch collectors and repo-specific lane wrappers."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signals_engine.core import RunContext, RunStatus
from signals_engine.sources.github.content import ContentResult
from signals_engine.sources.github.releases import Release


class TestGitHubRepoSpecificLanes(unittest.TestCase):
    def _make_ctx(self, tmp_dir: str, lane: str, lane_config: dict) -> RunContext:
        ctx = RunContext(
            lane=lane,
            date="2026-04-11",
            data_dir=Path(tmp_dir),
            config={"lanes": {lane: lane_config}},
        )
        ctx.ensure_dirs()
        return ctx

    def test_collect_single_repo_lane_fails_when_repo_missing(self):
        from signals_engine.lanes.claude_code_watch import collect_claude_code_watch

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                "claude-code-watch",
                {
                    "signals": {
                        "release": {"enabled": False},
                        "changelog": {"enabled": False},
                        "readme": {"enabled": False},
                    }
                },
            )

            result = collect_claude_code_watch(ctx)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(result.signals_written, 0)
        self.assertTrue(any("repo" in err.lower() for err in result.errors))

    def test_collect_single_repo_lane_fails_when_repo_invalid(self):
        from signals_engine.lanes.codex_watch import collect_codex_watch

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                "codex-watch",
                {
                    "repo": "openai-codex",
                    "signals": {
                        "release": {"enabled": False},
                        "changelog": {"enabled": False},
                        "readme": {"enabled": False},
                    },
                },
            )

            result = collect_codex_watch(ctx)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(result.signals_written, 0)
        self.assertTrue(any("invalid repo format" in err.lower() for err in result.errors))

    @patch("signals_engine.lanes.github_repo_watch.fetch_content")
    @patch("signals_engine.lanes.github_repo_watch.fetch_releases")
    def test_codex_lane_collects_single_repo_and_keeps_summary_schema(
        self,
        mock_fetch_releases,
        mock_fetch_content,
    ):
        from signals_engine.lanes.codex_watch import collect_codex_watch
        from signals_engine.runtime.run_manifest import render_run_manifest

        mock_fetch_releases.return_value = [
            Release(
                tag="v0.9.0",
                name="Codex v0.9.0",
                body="Release notes here",
                html_url="https://github.com/openai/codex/releases/tag/v0.9.0",
                published_at="2026-04-11T08:00:00Z",
                prerelease=False,
                assets=[],
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                "codex-watch",
                {
                    "repo": "openai/codex",
                    "signals": {
                        "release": {"enabled": True, "lookback_days": 7, "max_per_repo": 3},
                        "changelog": {"enabled": False},
                        "readme": {"enabled": False},
                    },
                },
            )

            result = collect_codex_watch(ctx)
            manifest = render_run_manifest(result)

        self.assertEqual(result.status, RunStatus.SUCCESS)
        self.assertEqual(result.repos_checked, 1)
        self.assertEqual(result.signals_written, 1)
        self.assertEqual(result.signal_records[0].lane, "codex-watch")
        self.assertEqual(mock_fetch_content.call_count, 0)
        self.assertEqual(manifest["summary"]["repos_checked"], 1)
        self.assertEqual(manifest["summary"]["signal_types"], {"release": 1})

    @patch("signals_engine.lanes.github_repo_watch.fetch_content")
    @patch("signals_engine.lanes.github_repo_watch.fetch_releases")
    def test_new_lane_does_not_reuse_legacy_changelog_state(
        self,
        mock_fetch_releases,
        mock_fetch_content,
    ):
        from signals_engine.lanes.github_watch import collect_github_watch
        from signals_engine.lanes.openclaw_watch import collect_openclaw_watch

        mock_fetch_releases.return_value = []
        mock_fetch_content.side_effect = [
            ContentResult(content="legacy baseline\n", sha="sha-1", path="CHANGELOG.md"),
            ContentResult(content="new lane content\n", sha="sha-2", path="CHANGELOG.md"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            legacy_ctx = RunContext(
                lane="github-watch",
                date="2026-04-11",
                data_dir=Path(tmp),
                config={
                    "lanes": {
                        "github-watch": {
                            "repos": ["openclaw/openclaw"],
                            "signals": {
                                "release": {"enabled": False},
                                "changelog": {"enabled": True, "files": ["CHANGELOG.md"]},
                                "readme": {"enabled": False},
                            },
                        }
                    }
                },
            )
            legacy_ctx.ensure_dirs()
            legacy_result = collect_github_watch(legacy_ctx)

            new_ctx = self._make_ctx(
                tmp,
                "openclaw-watch",
                {
                    "repo": "openclaw/openclaw",
                    "signals": {
                        "release": {"enabled": False},
                        "changelog": {"enabled": True, "files": ["CHANGELOG.md"]},
                        "readme": {"enabled": False},
                    },
                },
            )
            new_result = collect_openclaw_watch(new_ctx)

        self.assertEqual(legacy_result.status, RunStatus.EMPTY)
        self.assertEqual(new_result.status, RunStatus.EMPTY)
        self.assertEqual(new_result.signals_written, 0)

    @patch("signals_engine.lanes.github_repo_watch.fetch_content")
    @patch("signals_engine.lanes.github_repo_watch.fetch_releases")
    def test_changelog_state_distinguishes_file_path(
        self,
        mock_fetch_releases,
        mock_fetch_content,
    ):
        from signals_engine.lanes.openclaw_watch import collect_openclaw_watch

        mock_fetch_releases.return_value = []
        mock_fetch_content.side_effect = [
            ContentResult(content="from changelog\n", sha="sha-1", path="CHANGELOG.md"),
            ContentResult(content="from changes\n", sha="sha-2", path="CHANGES.md"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            first_ctx = self._make_ctx(
                tmp,
                "openclaw-watch",
                {
                    "repo": "openclaw/openclaw",
                    "signals": {
                        "release": {"enabled": False},
                        "changelog": {"enabled": True, "files": ["CHANGELOG.md"]},
                        "readme": {"enabled": False},
                    },
                },
            )
            first_result = collect_openclaw_watch(first_ctx)

            second_ctx = self._make_ctx(
                tmp,
                "openclaw-watch",
                {
                    "repo": "openclaw/openclaw",
                    "signals": {
                        "release": {"enabled": False},
                        "changelog": {"enabled": True, "files": ["CHANGES.md"]},
                        "readme": {"enabled": False},
                    },
                },
            )
            second_result = collect_openclaw_watch(second_ctx)

        self.assertEqual(first_result.status, RunStatus.EMPTY)
        self.assertEqual(second_result.status, RunStatus.EMPTY)
        self.assertEqual(second_result.signals_written, 0)


class TestGitHubLaneListing(unittest.TestCase):
    def test_lanes_list_includes_repo_specific_github_lanes(self):
        result = subprocess.run(
            [sys.executable, "-m", "signals_engine.cli", "lanes", "list"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env={**subprocess.os.environ, "PYTHONPATH": "src"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        stdout_lines = set(result.stdout.splitlines())
        self.assertIn("github-watch", stdout_lines)
        self.assertIn("claude-code-watch", stdout_lines)
        self.assertIn("openclaw-watch", stdout_lines)
        self.assertIn("codex-watch", stdout_lines)
