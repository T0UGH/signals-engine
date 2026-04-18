"""Lane registry — maps lane name to collector callable."""
from typing import Callable
from ..core import RunResult, RunContext


CollectorFn = Callable[[RunContext], RunResult]


LANE_REGISTRY: dict[str, CollectorFn | None] = {
    "x-feed": None,  # filled by lanes.x_feed
    "x-following": None,  # filled by lanes.x_following
    "github-watch": None,  # filled by lanes.github_watch
    "claude-code-watch": None,  # filled by lanes.claude_code_watch
    "openclaw-watch": None,  # filled by lanes.openclaw_watch
    "codex-watch": None,  # filled by lanes.codex_watch
    "reddit-watch": None,  # filled by lanes.reddit_watch
    "hacker-news-watch": None,  # filled by lanes.hacker_news_watch
    "hacker-news-search-watch": None,  # filled by lanes.hacker_news_search_watch
    "github-trending-weekly": None,  # filled by lanes.github_trending_weekly
    "product-hunt-watch": None,  # filled by lanes.product_hunt_watch
    "polymarket-watch": None,  # filled by lanes.polymarket_watch
    "weather-watch": None,  # filled by lanes.weather_watch
}


def get_lane_collector(lane: str) -> CollectorFn | None:
    """Return the collector for a given lane, or None if not registered."""
    return LANE_REGISTRY.get(lane)


def register_lane(lane: str, collector: CollectorFn) -> None:
    """Register a lane collector at runtime."""
    LANE_REGISTRY[lane] = collector
