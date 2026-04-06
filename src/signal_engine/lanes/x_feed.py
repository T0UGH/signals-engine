"""x-feed lane collector stub."""
from ..core import RunResult, RunContext, RunStatus
from .registry import register_lane


def collect_x_feed(ctx: RunContext) -> RunResult:
    """Collect x-feed signals (stub — Phase 1)."""
    return RunResult(
        lane="x-feed",
        date=ctx.date,
        status=RunStatus.EMPTY,
        started_at="",
        finished_at="",
        warnings=["x-feed collector not yet implemented"],
        errors=[],
        signal_records=[],
        repos_checked=0,
        signals_written=0,
        signal_types_count={},
        index_file=None,
    )


register_lane("x-feed", collect_x_feed)
