"""openclaw-watch lane collector."""
from ..core import RunContext, RunResult
from .github_repo_watch import collect_github_repo_watch
from .registry import register_lane


def collect_openclaw_watch(ctx: RunContext) -> RunResult:
    """Collect GitHub signals for the OpenClaw repo lane."""
    return collect_github_repo_watch(ctx, lane_name="openclaw-watch")


register_lane("openclaw-watch", collect_openclaw_watch)
