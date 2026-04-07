"""Tests for product-hunt-watch lane and source."""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from signals_engine.sources.producthunt import (
    _to_slug,
    _parse_post,
    match_posts_by_topics,
    PHError,
    Post,
    Topic,
    Maker,
)
from signals_engine.lanes.product_hunt_watch import (
    _escape_yaml,
    _build_signal,
)
from signals_engine.core import RunContext, RunStatus


class TestToSlug(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_to_slug("Artificial Intelligence"), "artificial-intelligence")

    def test_lowercase(self):
        self.assertEqual(_to_slug("Developer Tools"), "developer-tools")

    def test_productivity(self):
        self.assertEqual(_to_slug("Productivity"), "productivity")


class TestParsePost(unittest.TestCase):
    def _make_node(self, **overrides):
        defaults = {
            "id": "123",
            "slug": "my-product",
            "name": "My Product",
            "tagline": "A great product",
            "description": "This does something amazing",
            "votesCount": 500,
            "commentsCount": 42,
            "createdAt": "2026-04-07T10:00:00Z",
            "featuredAt": "2026-04-07T12:00:00Z",
            "website": "https://myproduct.com",
            "url": "https://www.producthunt.com/posts/my-product",
            "topics": {"edges": [
                {"node": {"slug": "artificial-intelligence", "name": "Artificial Intelligence"}},
                {"node": {"slug": "developer-tools", "name": "Developer Tools"}},
            ]},
            "makers": [
                {"name": "Alice", "username": "alice"},
                {"name": "Bob", "username": "bob"},
            ],
        }
        defaults.update(overrides)
        return defaults

    def test_parses_basic_fields(self):
        node = self._make_node()
        post = _parse_post(node)
        self.assertEqual(post.id, "123")
        self.assertEqual(post.slug, "my-product")
        self.assertEqual(post.name, "My Product")
        self.assertEqual(post.votes_count, 500)
        self.assertEqual(post.comments_count, 42)
        self.assertTrue(post.is_featured)

    def test_topics_parsed(self):
        node = self._make_node()
        post = _parse_post(node)
        self.assertEqual(len(post.topics), 2)
        slugs = {t.slug for t in post.topics}
        self.assertIn("artificial-intelligence", slugs)
        self.assertIn("developer-tools", slugs)

    def test_makers_parsed(self):
        node = self._make_node()
        post = _parse_post(node)
        self.assertEqual(len(post.makers), 2)
        usernames = {m.username for m in post.makers}
        self.assertIn("alice", usernames)
        self.assertIn("bob", usernames)

    def test_not_featured_when_no_featuredAt(self):
        node = self._make_node(featuredAt="")
        post = _parse_post(node)
        self.assertFalse(post.is_featured)

    def test_missing_optional_fields(self):
        node = self._make_node(
            tagline=None,
            description=None,
            website=None,
        )
        post = _parse_post(node)
        self.assertEqual(post.tagline, "")  # None -> "" via str(None or "")
        self.assertEqual(post.description, "")


class TestMatchPostsByTopics(unittest.TestCase):
    def _make_post(self, topic_slugs: list[str]) -> Post:
        topics = [Topic(slug=s, name=s.title()) for s in topic_slugs]
        return Post(
            id="1", slug="p", name="P", tagline="", description="",
            votes_count=100, comments_count=0, created_at="", featured_at="2026-04-07T00:00:00Z",
            website="", url="", topics=topics, makers=[],
        )

    def test_matches_single_topic(self):
        posts = [self._make_post(["artificial-intelligence"])]
        hits = match_posts_by_topics(posts, ["Artificial Intelligence"])
        self.assertEqual(len(hits), 1)

    def test_no_match_different_topic(self):
        posts = [self._make_post(["developer-tools"])]
        hits = match_posts_by_topics(posts, ["Productivity"])
        self.assertEqual(len(hits), 0)

    def test_unfeatured_not_matched(self):
        post = Post(
            id="1", slug="p", name="P", tagline="", description="",
            votes_count=100, comments_count=0, created_at="", featured_at="",
            website="", url="", topics=[Topic(slug="ai", name="AI")], makers=[],
        )
        hits = match_posts_by_topics([post], ["Artificial Intelligence"])
        self.assertEqual(len(hits), 0)

    def test_one_signal_per_post_even_if_multiple_topic_matches(self):
        post = Post(
            id="1", slug="p", name="P", tagline="", description="",
            votes_count=100, comments_count=0, created_at="", featured_at="2026-04-07T00:00:00Z",
            website="", url="",
            topics=[
                Topic(slug="artificial-intelligence", name="AI"),
                Topic(slug="developer-tools", name="DevTools"),
            ],
            makers=[],
        )
        hits = match_posts_by_topics([post], ["Artificial Intelligence", "Developer Tools"])
        # Should be 1, not 2 — one signal per post per run
        self.assertEqual(len(hits), 1)


class TestEscapeYaml(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_escape_yaml("hello"), "hello")

    def test_escapes_double_quote(self):
        self.assertEqual(_escape_yaml('say "hello"'), 'say \\"hello\\"')

    def test_escapes_backslash(self):
        self.assertEqual(_escape_yaml("path\\to\\file"), "path\\\\to\\\\file")

    def test_removes_newlines(self):
        self.assertEqual(_escape_yaml("line1\nline2"), "line1 line2")


class TestCollectProductHuntIntegration(unittest.TestCase):
    """Integration tests using mocked Product Hunt API."""

    def _make_ctx(self, tmp_dir, topics=None) -> RunContext:
        import tempfile
        from pathlib import Path
        config = {
            "lanes": {
                "product-hunt-watch": {
                    "api": {
                        "token_env": "PH_API_TOKEN",
                        "lookback_days": 1,
                        "max_pages": 1,
                        "max_per_topic": 20,
                    },
                    "topics": topics or ["Artificial Intelligence", "Developer Tools"],
                }
            }
        }
        return RunContext(
            lane="product-hunt-watch",
            date="2026-04-08",
            config=config,
            data_dir=Path(tmp_dir),
        )

    def _mock_post_node(self, name, slug, topics, votes=100, featured="2026-04-07T00:00:00Z"):
        return {
            "id": f"id-{slug}",
            "slug": slug,
            "name": name,
            "tagline": f"{name} tagline",
            "description": f"{name} description",
            "votesCount": votes,
            "commentsCount": 10,
            "createdAt": "2026-04-07T00:00:00Z",
            "featuredAt": featured,
            "website": f"https://{slug}.com",
            "url": f"https://www.producthunt.com/posts/{slug}",
            "topics": {"edges": [{"node": {"slug": t, "name": t.title()}} for t in topics]},
            "makers": [{"name": "Alice", "username": "alice"}],
        }

    @patch("signals_engine.lanes.product_hunt_watch.fetch_posts")
    def test_collect_success(self, mock_fetch):
        import tempfile
        mock_fetch.return_value = [
            _parse_post(self._mock_post_node("AI Tool", "ai-tool", ["artificial-intelligence"], votes=300)),
            _parse_post(self._mock_post_node("Dev Tool", "dev-tool", ["developer-tools"], votes=200)),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp)
            from signals_engine.lanes.product_hunt_watch import collect_product_hunt_watch
            with patch.dict("os.environ", {"PH_API_TOKEN": "fake-token"}):
                result = collect_product_hunt_watch(ctx)

        self.assertEqual(result.status, RunStatus.SUCCESS)
        self.assertEqual(result.signals_written, 2)
        slugs = {r.entity_id for r in result.signal_records}
        self.assertIn("ai-tool", slugs)
        self.assertIn("dev-tool", slugs)

    @patch("signals_engine.lanes.product_hunt_watch.fetch_posts")
    def test_collect_empty_when_no_topics_match(self, mock_fetch):
        import tempfile
        mock_fetch.return_value = [
            _parse_post(self._mock_post_node("Random", "random", ["gaming"], votes=100)),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, topics=["Artificial Intelligence"])
            from signals_engine.lanes.product_hunt_watch import collect_product_hunt_watch
            with patch.dict("os.environ", {"PH_API_TOKEN": "fake-token"}):
                result = collect_product_hunt_watch(ctx)

        self.assertEqual(result.status, RunStatus.EMPTY)
        self.assertEqual(result.signals_written, 0)

    @patch("signals_engine.lanes.product_hunt_watch.fetch_posts")
    def test_collect_api_error(self, mock_fetch):
        import tempfile
        mock_fetch.side_effect = PHError("GraphQL error: invalid token")

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp)
            from signals_engine.lanes.product_hunt_watch import collect_product_hunt_watch
            with patch.dict("os.environ", {"PH_API_TOKEN": "fake-token"}):
                result = collect_product_hunt_watch(ctx)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertIn("Product Hunt API error", result.errors[0])

    def test_collect_skips_when_no_token(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp)
            from signals_engine.lanes.product_hunt_watch import collect_product_hunt_watch
            with patch.dict("os.environ", {}, clear=True):
                result = collect_product_hunt_watch(ctx)

        self.assertEqual(result.status, RunStatus.EMPTY)
        self.assertIn("PH_API_TOKEN not set", result.warnings[0])

    @patch("signals_engine.lanes.product_hunt_watch.fetch_posts")
    def test_max_per_topic_respected(self, mock_fetch):
        import tempfile
        # Two posts in the same topic
        mock_fetch.return_value = [
            _parse_post(self._mock_post_node("AI Tool 1", "ai-tool-1", ["artificial-intelligence"], votes=300)),
            _parse_post(self._mock_post_node("AI Tool 2", "ai-tool-2", ["artificial-intelligence"], votes=200)),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, topics=["Artificial Intelligence"])
            ctx.config["lanes"]["product-hunt-watch"]["api"]["max_per_topic"] = 1
            from signals_engine.lanes.product_hunt_watch import collect_product_hunt_watch
            with patch.dict("os.environ", {"PH_API_TOKEN": "fake-token"}):
                result = collect_product_hunt_watch(ctx)

        # Only 1 should be written (max_per_topic=1)
        self.assertEqual(result.signals_written, 1)

    @patch("signals_engine.lanes.product_hunt_watch.fetch_posts")
    def test_signal_record_has_correct_fields(self, mock_fetch):
        import tempfile
        # Note: topic name should be human-readable "Artificial Intelligence", not the slug
        mock_fetch.return_value = [
            _parse_post({
                **self._mock_post_node("AI Tool", "ai-tool", ["artificial-intelligence"], votes=500),
                "topics": {"edges": [
                    {"node": {"slug": "artificial-intelligence", "name": "Artificial Intelligence"}},
                ]},
            }),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp)
            from signals_engine.lanes.product_hunt_watch import collect_product_hunt_watch
            with patch.dict("os.environ", {"PH_API_TOKEN": "fake-token"}):
                result = collect_product_hunt_watch(ctx)

        rec = result.signal_records[0]
        self.assertEqual(rec.lane, "product-hunt-watch")
        self.assertEqual(rec.signal_type, "producthunt_topic_hit")
        self.assertEqual(rec.source, "producthunt")
        self.assertEqual(rec.entity_id, "ai-tool")
        self.assertEqual(rec.likes, 500)  # votes_count mapped to likes
        self.assertEqual(rec.group, "Artificial Intelligence")  # topic name
