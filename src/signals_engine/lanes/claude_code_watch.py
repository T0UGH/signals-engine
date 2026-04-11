"""claude-code-watch lane collector."""
from ..core import RunContext, RunResult
from .github_repo_watch import collect_github_repo_watch
from .registry import register_lane


def collect_claude_code_watch(ctx: RunContext) -> RunResult:
    """Collect GitHub signals for anthropics/claude-code style lanes."""
    return collect_github_repo_watch(ctx, lane_name="claude-code-watch")


register_lane("claude-code-watch", collect_claude_code_watch)
