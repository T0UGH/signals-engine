"""Legacy github-watch lane collector."""
from ..core import RunContext, RunResult
from .github_repo_watch import collect_github_repos_watch
from .registry import register_lane


def collect_github_watch(ctx: RunContext) -> RunResult:
    """Collect GitHub signals for the legacy multi-repo lane."""
    lane_config = ctx.config.get("lanes", {}).get("github-watch", {})
    repos = list(lane_config.get("repos", []))
    signals_cfg = lane_config.get("signals", {})

    return collect_github_repos_watch(
        ctx,
        lane_name="github-watch",
        repos=repos,
        signals_cfg=signals_cfg,
        invalid_repo_is_error=False,
    )


register_lane("github-watch", collect_github_watch)
