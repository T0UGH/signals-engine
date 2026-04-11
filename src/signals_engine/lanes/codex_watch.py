"""codex-watch lane collector."""
from ..core import RunContext, RunResult
from .github_repo_watch import collect_github_repo_watch
from .registry import register_lane


def collect_codex_watch(ctx: RunContext) -> RunResult:
    """Collect GitHub signals for the Codex repo lane."""
    return collect_github_repo_watch(ctx, lane_name="codex-watch")


register_lane("codex-watch", collect_codex_watch)
