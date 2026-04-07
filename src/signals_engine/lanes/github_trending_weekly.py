"""github-trending-weekly lane collector.

Collects the GitHub Trending Weekly repo list, optionally enriched with README.
No authentication required — GitHub trending pages are public.
"""
from datetime import datetime, timezone
from pathlib import Path

from ..core import RunResult, RunContext, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..sources.github_trending import fetch_trending_weekly, TrendingError
from ..sources.github import fetch_content
from ..signals.writer import write_signal
from ..signals.index import write_index
from ..runtime.run_manifest import write_run_manifest
from .registry import register_lane


_MAX_README_SIZE = 102400


def _truncate_readme(content: str, max_size: int = _MAX_README_SIZE) -> str:
    if len(content.encode("utf-8")) <= max_size:
        return content
    truncated = content[:max_size]
    original_kb = len(content.encode("utf-8")) // 1024
    return truncated + f"\n\n<!-- truncated, original size: {original_kb} KB -->"


def _safe(text: str) -> str:
    """Escape a string for use in YAML double-quoted value."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "").strip()


def _build_signal(
    ctx: RunContext,
    repo_rank: int,
    repo: str,
    description: str,
    language: str,
    stars_this_week: int,
    readme_content: str | None,
) -> SignalRecord:
    """Build and write one trending repo signal."""
    owner, repo_name = repo.split("/", 1)
    filename = f"{owner}__{repo_name}__trending-weekly.md"
    file_path = str(ctx.signals_dir / filename)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    # Build body
    body_lines = [
        "## Trending Context\n",
        f"- Rank: #{repo_rank} on GitHub Trending Weekly\n",
        f"- Language: {language or 'unknown'}\n",
        f"- Stars this week: {stars_this_week:,}\n\n",
        "## Description\n\n",
        f"{description or '(no description)'}\n",
    ]
    if readme_content:
        body_lines.extend([
            "\n## README\n\n",
            f"{readme_content}\n",
        ])

    record = SignalRecord(
        lane="github-trending-weekly",
        signal_type="trending-weekly",
        source="github-trending",
        entity_type="repo",
        entity_id=repo,
        title=repo_name,
        source_url=f"https://github.com/{repo}",
        fetched_at=fetched_at,
        file_path=file_path,
        # github-trending-specific
        session_id="",
        handle=repo,
        post_id=str(repo_rank),
        created_at="",
        # enrichment fields repurposed for trending context
        text_preview=description[:200] if description else "",
        likes=stars_this_week,  # reuse likes field for stars_this_week
        group=language or "unknown",
    )
    write_signal(record)
    return record


def collect_github_trending_weekly(ctx: RunContext) -> RunResult:
    """Collect github-trending-weekly signals.

    Config keys read:
        lanes["github-trending-weekly"]["trending"]["url"]          (default: weekly)
        lanes["github-trending-weekly"]["trending"]["max_repos"]   (default: 30)
        lanes["github-trending-weekly"]["readme"]["enabled"]       (default: true)
        lanes["github-trending-weekly"]["readme"]["max_size"]      (default: 102400)

    Run status semantics:
        - at least one repo fetched -> SUCCESS (even if 0 repos on trending)
        - network/API error prevents fetching -> FAILED
    """
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    warnings: list[str] = []
    errors: list[str] = []

    lane_config = ctx.config.get("lanes", {}).get("github-trending-weekly", {})
    trending_cfg = lane_config.get("trending", {})
    trending_url = trending_cfg.get("url", "https://github.com/trending?since=weekly")
    max_repos = int(trending_cfg.get("max_repos", 30))

    readme_cfg = lane_config.get("readme", {})
    readme_enabled = readme_cfg.get("enabled", True)
    readme_max_size = int(readme_cfg.get("max_size", 102400))

    debug_log(f"[github-trending-weekly] START url={trending_url} max_repos={max_repos}", log_file=ctx.debug_log_path)

    all_records: list[SignalRecord] = []

    try:
        trending_repos = fetch_trending_weekly(
            url=trending_url,
            max_repos=max_repos,
            timeout=30,
        )
        debug_log(f"[github-trending-weekly] parsed {len(trending_repos)} repos", log_file=ctx.debug_log_path)
    except TrendingError as e:
        debug_log(f"[github-trending-weekly] fetch error: {e}", log_file=ctx.debug_log_path)
        errors.append(f"trending fetch failed: {e}")
        trending_repos = []

    for tr in trending_repos:
        owner, repo_name = tr.repo.split("/", 1)
        debug_log(f"[github-trending-weekly] [{tr.rank}] {tr.repo}", log_file=ctx.debug_log_path)

        readme_content: str | None = None
        if readme_enabled:
            try:
                result = fetch_content(owner, repo_name, "README.md")
                if result:
                    readme_content = _truncate_readme(result.content, readme_max_size)
                    debug_log(f"[github-trending-weekly]   + README ({len(readme_content)} chars)", log_file=ctx.debug_log_path)
                else:
                    debug_log(f"[github-trending-weekly]   . no README", log_file=ctx.debug_log_path)
            except Exception as e:
                debug_log(f"[github-trending-weekly]   WARN: README fetch failed: {e}", log_file=ctx.debug_log_path)
                warnings.append(f"{tr.repo} README: {e}")

        try:
            record = _build_signal(
                ctx=ctx,
                repo_rank=tr.rank,
                repo=tr.repo,
                description=tr.description,
                language=tr.language,
                stars_this_week=tr.stars_this_week,
                readme_content=readme_content,
            )
            all_records.append(record)
        except Exception as e:
            debug_log(f"[github-trending-weekly]   ERROR writing signal: {e}", log_file=ctx.debug_log_path)
            errors.append(f"failed to write signal for {tr.repo}: {e}")

    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    signal_types_count: dict[str, int] = {}
    for r in all_records:
        signal_types_count[r.signal_type] = signal_types_count.get(r.signal_type, 0) + 1

    if all_records:
        status = RunStatus.SUCCESS
    elif errors:
        status = RunStatus.FAILED
    else:
        status = RunStatus.EMPTY

    index_path = ctx.index_path
    run_json_path = ctx.run_json_path

    result = RunResult(
        lane="github-trending-weekly",
        date=ctx.date,
        status=status,
        started_at=started_at,
        session_id=None,
        finished_at=finished_at,
        warnings=warnings,
        errors=errors,
        signal_records=all_records,
        repos_checked=len(trending_repos),
        signals_written=len(all_records),
        signal_types_count=signal_types_count,
        index_file=str(index_path),
    )

    debug_log(f"[github-trending-weekly] INDEX WRITE status={result.status.value}", log_file=ctx.debug_log_path)
    index_ok = _write_index_to_file(result, index_path)
    if errors or not index_ok:
        result.status = RunStatus.FAILED

    _write_manifest_to_file(result, run_json_path)
    debug_log(f"[github-trending-weekly] END signals={len(all_records)} repos={len(trending_repos)}", log_file=ctx.debug_log_path)

    return result


def _write_index_to_file(result: RunResult, index_path: Path) -> bool:
    try:
        write_index(result, index_path)
        return True
    except Exception as e:
        result.errors.append(f"failed to write index.md: {e}")
        return False


def _write_manifest_to_file(result: RunResult, run_json_path: Path) -> bool:
    try:
        write_run_manifest(result, run_json_path)
        return True
    except Exception as e:
        result.errors.append(f"failed to write run.json: {e}")
        return False


register_lane("github-trending-weekly", collect_github_trending_weekly)
