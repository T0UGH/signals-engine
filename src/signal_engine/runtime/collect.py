"""Collect orchestration entry point."""
from ..core import RunContext, RunResult, RunStatus


def collect_lane(ctx: RunContext) -> RunResult:
    """Run collect for the lane specified in the context."""
    from ..lanes.registry import get_lane_collector
    collector = get_lane_collector(ctx.lane)
    return collector(ctx)
