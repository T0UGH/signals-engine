"""Lane registry — maps lane name to collector callable."""
from typing import Callable
from ..core import RunResult, RunContext


CollectorFn = Callable[[RunContext], RunResult]


LANE_REGISTRY: dict[str, CollectorFn | None] = {
    "x-feed": None,  # filled by lanes.x_feed
    "x-following": None,  # filled by lanes.x_following
}


def get_lane_collector(lane: str) -> CollectorFn | None:
    """Return the collector for a given lane, or None if not registered."""
    return LANE_REGISTRY.get(lane)


def register_lane(lane: str, collector: CollectorFn) -> None:
    """Register a lane collector at runtime."""
    LANE_REGISTRY[lane] = collector
