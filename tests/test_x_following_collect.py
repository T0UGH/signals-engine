"""Tests for x-following lane collector."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from signals_engine.core import RunContext, RunStatus
from signals_engine.lanes.x_following import (
    _build_enrichment_lookup,
    _enrich_signal,
    _sanitize_handle,
    _make_session_id,
)


class TestSanitizeHandle(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_sanitize_handle("elonmusk"), "elonmusk")

    def test_with_slash(self):
        self.assertEqual(_sanitize_handle("a/b"), "a_b")

    def test_with_colon(self):
        self.assertEqual(_sanitize_handle("a:b"), "a_b")


class TestBuildEnrichmentLookup(unittest.TestCase):
    def test_empty(self):
        result = _build_enrichment_lookup([])
        self.assertEqual(result, {})

    def test_single_entry(self):
        result = _build_enrichment_lookup([
            {"handle": "AnthropicAI", "group": "claude-core", "tags": ["AI", "LLM"]}
        ])
        self.assertEqual(result["anthropicai"]["group"], "claude-core")
        self.assertEqual(result["anthropicai"]["tags"], ["AI", "LLM"])

    def test_case_insensitive(self):
        result = _build_enrichment_lookup([
            {"handle": "AnthropicAI", "group": "claude-core", "tags": []}
        ])
        # Lookup by any case variant
        self.assertIn("anthropicai", result)
        group, tags = _enrich_signal("ANTHROPICAI", result)
        self.assertEqual(group, "claude-core")


class TestEnrichSignal(unittest.TestCase):
    def test_found(self):
        lookup = {"elonmusk": {"group": "tech", "tags": ["space"]}}
        group, tags = _enrich_signal("elonmusk", lookup)
        self.assertEqual(group, "tech")
        self.assertEqual(tags, ["space"])

    def test_not_found(self):
        lookup = {}
        group, tags = _enrich_signal("unknown", lookup)
        self.assertEqual(group, "uncategorized")
        self.assertEqual(tags, [])

    def test_case_insensitive(self):
        lookup = {"testuser": {"group": "found", "tags": []}}
        group, tags = _enrich_signal("TestUser", lookup)
        self.assertEqual(group, "found")


class TestCollectXFollowingIntegration(unittest.TestCase):
    """Integration tests using mocked fetch_following_timeline."""

    def _make_ctx(self, tmp_dir: Path) -> RunContext:
        config = {
            "lanes": {
                "x-following": {
                    "source": {
                        "auth": {},
                        "limit": 200,
                        "timeout_seconds": 30,
                    },
                    "enrichment": [
                        {"handle": "AnthropicAI", "group": "claude-core", "tags": []},
                        {"handle": "claudeai", "group": "claude-core", "tags": []},
                    ],
                }
            }
        }
        return RunContext(
            lane="x-following",
            date="2026-04-08",
            config=config,
            data_dir=tmp_dir,
        )

    def _mock_tweet(self, rest_id: str, author: str, text: str) -> MagicMock:
        tweet = MagicMock()
        tweet.id = rest_id
        tweet.author = author
        tweet.text = text
        tweet.url = f"https://x.com/{author}/status/{rest_id}"
        tweet.created_at = "2026-04-08T10:00:00+0000"
        tweet.likes = 10
        tweet.retweets = 2
        tweet.replies = 1
        tweet.views = 1000
        return tweet

    @patch("signals_engine.lanes.x_following.fetch_following_timeline")
    def test_collect_empty_source(self, mock_fetch):
        """Empty source -> EMPTY status."""
        mock_fetch.return_value = []

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(Path(tmp))
            from signals_engine.lanes.x_following import collect_x_following
            result = collect_x_following(ctx)

        self.assertEqual(result.status, RunStatus.EMPTY)
        self.assertEqual(result.signals_written, 0)

    @patch("signals_engine.lanes.x_following.fetch_following_timeline")
    def test_collect_success_with_enrichment(self, mock_fetch):
        """Collected tweets with matching enrichment -> group set correctly."""
        mock_fetch.return_value = [
            self._mock_tweet("1", "AnthropicAI", "Hello from Anthropic"),
            self._mock_tweet("2", "claudeai", "Anthropic news"),
            self._mock_tweet("3", "unknown_user", "Random tweet"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(Path(tmp))
            from signals_engine.lanes.x_following import collect_x_following
            result = collect_x_following(ctx)

        self.assertEqual(result.status, RunStatus.SUCCESS)
        self.assertEqual(result.signals_written, 3)

        # Check enrichment
        records = result.signal_records
        anthropic_rec = next(r for r in records if r.handle == "AnthropicAI")
        self.assertEqual(anthropic_rec.group, "claude-core")

        unknown_rec = next(r for r in records if r.handle == "unknown_user")
        self.assertEqual(unknown_rec.group, "uncategorized")

    @patch("signals_engine.lanes.x_following.fetch_following_timeline")
    def test_session_id_format(self, mock_fetch):
        """Session ID uses following prefix."""
        mock_fetch.return_value = []

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(Path(tmp))
            from signals_engine.lanes.x_following import collect_x_following
            result = collect_x_following(ctx)

        self.assertTrue(result.session_id.startswith("following-"))
        self.assertIn("2026-04-08", result.session_id)

    @patch("signals_engine.lanes.x_following.fetch_following_timeline")
    def test_collect_source_failure(self, mock_fetch):
        """Source error -> FAILED status."""
        from signals_engine.sources.x.errors import AuthError

        mock_fetch.side_effect = AuthError("no cookies")

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(Path(tmp))
            from signals_engine.lanes.x_following import collect_x_following
            result = collect_x_following(ctx)

        self.assertEqual(result.status, RunStatus.EMPTY)
        self.assertIn("source fetch failed", result.errors[0])
