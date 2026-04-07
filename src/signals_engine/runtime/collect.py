"""Collect orchestration entry point."""
from ..core import RunContext, RunResult
from ..core.debuglog import debug_log


def collect_lane(ctx: RunContext) -> RunResult:
    """Run collect for the lane specified in the context."""
    # Trigger lane registration side effects by importing lane modules.
    # Each lane module calls register_lane() at module level when imported.
    import importlib
    from ..lanes.registry import LANE_REGISTRY

    # Ensure all known lane modules are imported to trigger their registration.
    # The registry dict holds collector functions, which are filled by
    # each lane module's register_lane() call.
    for lane_name in LANE_REGISTRY:
        try:
            importlib.import_module(f"..lanes.{_lane_module_name(lane_name)}", package=__package__)
        except ImportError as e:
            debug_log(f"[collect] Could not import lane module '{lane_name}': {e}")

    from ..lanes.registry import get_lane_collector
    collector = get_lane_collector(ctx.lane)
    if collector is None:
        raise ValueError(f"No collector registered for lane: {ctx.lane}")
    return collector(ctx)


def _lane_module_name(lane: str) -> str:
    """Map lane name to module name."""
    # x-feed -> x_feed, github-watch -> github_watch
    return lane.replace("-", "_")
