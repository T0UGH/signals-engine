"""github-watch lane collector.

Monitors a watchlist of GitHub repositories for:
- new releases (within a lookback window)
- changelog file changes (CHANGELOG.md, etc.)
- README changes

State is maintained per repo per signal type, enabling change detection.
"""
from datetime import datetime, timezone
from pathlib import Path

from ..core import RunResult, RunContext, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..sources.github import fetch_releases, fetch_content, diff_content
from ..sources.github.releases import GhError
from ..signals.writer import write_signal
from ..signals.index import write_index
from ..runtime.run_manifest import write_run_manifest
from .registry import register_lane

# Content truncation threshold
_MAX_CONTENT_SIZE = 102400


def _sanitize(text: str) -> str:
    """Remove newlines from a string for use in a single-line context."""
    return text.replace("\n", " ").replace("\r", "").strip()


def _truncate(content: str, max_size: int = _MAX_CONTENT_SIZE) -> str:
    """Truncate content if it exceeds max_size bytes."""
    if len(content.encode("utf-8")) <= max_size:
        return content
    truncated = content[:max_size]
    original_kb = len(content.encode("utf-8")) // 1024
    return truncated + f"\n\n<!-- truncated, original size: {original_kb} KB -->"


def _safe_filename(text: str) -> str:
    """Make text safe for use in a filename."""
    return text.replace("/", "-").replace(" ", "-").replace(":", "-").replace("\\", "-")


def _state_path(state_dir: Path, owner: str, repo: str, signal_type: str) -> Path:
    """Return path to the state file for a given repo+signal_type."""
    return state_dir / f"{owner}__{repo}__{signal_type}.md"


def _read_state(state_path: Path) -> str | None:
    """Read state file content, or None if not found."""
    if state_path.exists():
        return state_path.read_text(encoding="utf-8")
    return None


def _write_state(state_path: Path, content: str) -> None:
    """Atomically write state file."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(state_path)


def _build_release_signal(
    ctx: RunContext,
    owner: str,
    repo: str,
    tag: str,
    name: str,
    body: str,
    html_url: str,
    published_at: str,
    prerelease: bool,
    assets: list[dict],
) -> SignalRecord:
    """Build a release SignalRecord and write the signal file."""
    safe_tag = _safe_filename(tag)
    filename = f"{owner}__{repo}__release__{safe_tag}.md"
    file_path = str(ctx.signals_dir / filename)

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    # Build body
    body_text = body if body else "(no release notes)"
    assets_lines = ""
    if assets:
        assets_lines = "\n## Assets\n\n" + "\n".join(
            f"- {a['Name']} ({a['size_mb']} MB)"
            for a in assets
        )

    record = SignalRecord(
        lane="github-watch",
        signal_type="release",
        source="github",
        entity_type="repo",
        entity_id=f"{owner}/{repo}",
        title=name or tag,
        source_url=html_url,
        fetched_at=fetched_at,
        file_path=file_path,
        # github-watch extras
        session_id="",
        handle=f"{owner}/{repo}",
        post_id=tag,
        created_at=published_at,
        prerelease=prerelease,
        release_assets=assets,
        release_body=body_text,
    )
    write_signal(record)
    return record


def _build_changelog_signal(
    ctx: RunContext,
    owner: str,
    repo: str,
    changelog_path: str,
    diff_text: str,
    stats: str,
) -> SignalRecord:
    """Build and write a changelog change signal."""
    filename = f"{owner}__{repo}__changelog__{ctx.date}.md"
    file_path = str(ctx.signals_dir / filename)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    title = f"{repo} CHANGELOG updated"

    record = SignalRecord(
        lane="github-watch",
        signal_type="changelog",
        source="github",
        entity_type="repo",
        entity_id=f"{owner}/{repo}",
        title=title,
        source_url=f"https://github.com/{owner}/{repo}/blob/HEAD/{changelog_path}",
        fetched_at=fetched_at,
        file_path=file_path,
        # extras
        session_id="",
        handle=f"{owner}/{repo}",
        post_id=changelog_path,
        created_at="",
        diff_stats=stats,
        diff_text=diff_text,
    )
    write_signal(record)
    return record


def _build_readme_signal(
    ctx: RunContext,
    owner: str,
    repo: str,
    diff_text: str,
    stats: str,
) -> SignalRecord:
    """Build and write a README change signal."""
    filename = f"{owner}__{repo}__readme__{ctx.date}.md"
    file_path = str(ctx.signals_dir / filename)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    title = f"{repo} README updated"

    record = SignalRecord(
        lane="github-watch",
        signal_type="readme",
        source="github",
        entity_type="repo",
        entity_id=f"{owner}/{repo}",
        title=title,
        source_url=f"https://github.com/{owner}/{repo}#readme",
        fetched_at=fetched_at,
        file_path=file_path,
        # extras
        session_id="",
        handle=f"{owner}/{repo}",
        post_id="README.md",
        created_at="",
        diff_stats=stats,
        diff_text=diff_text,
    )
    write_signal(record)
    return record


def _collect_releases_for_repo(
    ctx: RunContext,
    owner: str,
    repo: str,
    lookback_days: int,
    max_per_repo: int,
) -> list[SignalRecord]:
    """Collect release signals for one repo."""
    records: list[SignalRecord] = []
    try:
        releases = fetch_releases(owner, repo, lookback_days, max_per_repo)
    except GhError as e:
        debug_log(f"[github-watch] {owner}/{repo} releases GhError: {e}", log_file=ctx.debug_log_path)
        ctx.warnings.append(f"{owner}/{repo} releases: {e}")
        return []

    for rel in releases:
        try:
            record = _build_release_signal(
                ctx, owner, repo,
                tag=rel.tag,
                name=rel.name,
                body=rel.body,
                html_url=rel.html_url,
                published_at=rel.published_at,
                prerelease=rel.prerelease,
                assets=rel.assets,
            )
            records.append(record)
            debug_log(f"[github-watch] + release: {owner}/{repo} {rel.tag}", log_file=ctx.debug_log_path)
        except Exception as e:
            debug_log(f"[github-watch] failed to write release signal {owner}/{repo} {rel.tag}: {e}", log_file=ctx.debug_log_path)
            ctx.errors.append(f"failed to write release signal {rel.tag}: {e}")
    return records


def _collect_changelog_for_repo(
    ctx: RunContext,
    owner: str,
    repo: str,
    changelog_files: list[str],
) -> list[SignalRecord]:
    """Collect changelog change signals for one repo."""
    records: list[SignalRecord] = []
    state_dir = ctx.state_dir

    for changelog_path in changelog_files:
        try:
            result = fetch_content(owner, repo, changelog_path)
        except GhError as e:
            debug_log(f"[github-watch] {owner}/{repo} changelog {changelog_path} GhError: {e}", log_file=ctx.debug_log_path)
            ctx.warnings.append(f"{owner}/{repo} changelog {changelog_path}: {e}")
            continue

        if result is None:
            debug_log(f"[github-watch] . {owner}/{repo} changelog: not found", log_file=ctx.debug_log_path)
            continue

        content = _truncate(result.content)
        state_path = _state_path(state_dir, owner, repo, "changelog")
        old_content = _read_state(state_path)

        if old_content is None:
            # First run: save state, no signal
            _write_state(state_path, content)
            debug_log(f"[github-watch] ~ {owner}/{repo} changelog: first run, state saved", log_file=ctx.debug_log_path)
            continue

        diff_result = diff_content(old_content, content)
        if diff_result.is_first:
            _write_state(state_path, content)
            debug_log(f"[github-watch] ~ {owner}/{repo} changelog: first run, state saved", log_file=ctx.debug_log_path)
            continue

        if not diff_result.changed:
            debug_log(f"[github-watch] . {owner}/{repo} changelog: no change", log_file=ctx.debug_log_path)
            continue

        # Changed: emit signal + update state
        try:
            record = _build_changelog_signal(
                ctx, owner, repo, changelog_path,
                diff_text=diff_result.diff_text,
                stats=diff_result.stats,
            )
            records.append(record)
            _write_state(state_path, content)
            debug_log(f"[github-watch] + {owner}/{repo} changelog: ({diff_result.stats})", log_file=ctx.debug_log_path)
        except Exception as e:
            debug_log(f"[github-watch] failed to write changelog signal {owner}/{repo}: {e}", log_file=ctx.debug_log_path)
            ctx.errors.append(f"failed to write changelog signal: {e}")
        break  # Found first changelog, stop

    return records


def _collect_readme_for_repo(
    ctx: RunContext,
    owner: str,
    repo: str,
) -> list[SignalRecord]:
    """Collect README change signals for one repo."""
    records: list[SignalRecord] = []
    state_dir = ctx.state_dir

    try:
        result = fetch_content(owner, repo, "README.md")
    except GhError as e:
        debug_log(f"[github-watch] {owner}/{repo} README GhError: {e}", log_file=ctx.debug_log_path)
        ctx.warnings.append(f"{owner}/{repo} README: {e}")
        return []

    if result is None:
        debug_log(f"[github-watch] . {owner}/{repo} README: not found", log_file=ctx.debug_log_path)
        return []

    content = _truncate(result.content)
    state_path = _state_path(state_dir, owner, repo, "readme")
    old_content = _read_state(state_path)

    if old_content is None:
        _write_state(state_path, content)
        debug_log(f"[github-watch] ~ {owner}/{repo} README: first run, state saved", log_file=ctx.debug_log_path)
        return []

    diff_result = diff_content(old_content, content)
    if not diff_result.changed:
        debug_log(f"[github-watch] . {owner}/{repo} README: no change", log_file=ctx.debug_log_path)
        return []

    try:
        record = _build_readme_signal(
            ctx, owner, repo,
            diff_text=diff_result.diff_text,
            stats=diff_result.stats,
        )
        records.append(record)
        _write_state(state_path, content)
        debug_log(f"[github-watch] + {owner}/{repo} README: ({diff_result.stats})", log_file=ctx.debug_log_path)
    except Exception as e:
        debug_log(f"[github-watch] failed to write readme signal {owner}/{repo}: {e}", log_file=ctx.debug_log_path)
        ctx.errors.append(f"failed to write readme signal: {e}")

    return records


def collect_github_watch(ctx: RunContext) -> RunResult:
    """Collect github-watch signals for configured repos.

    Config keys read:
        lanes["github-watch"]["repos"]                    (list of "owner/repo")
        lanes["github-watch"]["signals"]["release"]["enabled"]          (default: true)
        lanes["github-watch"]["signals"]["release"]["lookback_days"]    (default: 7)
        lanes["github-watch"]["signals"]["release"]["max_per_repo"]     (default: 3)
        lanes["github-watch"]["signals"]["changelog"]["enabled"]        (default: true)
        lanes["github-watch"]["signals"]["changelog"]["files"]         (default: [CHANGELOG.md])
        lanes["github-watch"]["signals"]["readme"]["enabled"]           (default: true)

    Run status semantics:
        - at least one signal written -> SUCCESS
        - no signals written but all sources succeeded -> EMPTY
        - any source error that prevents normal operation -> FAILED
    """
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    lane_config = ctx.config.get("lanes", {}).get("github-watch", {})
    repos: list[str] = list(lane_config.get("repos", []))
    signals_cfg = lane_config.get("signals", {})

    release_cfg = signals_cfg.get("release", {})
    release_enabled = release_cfg.get("enabled", True)
    lookback_days = int(release_cfg.get("lookback_days", 7))
    max_per_repo = int(release_cfg.get("max_per_repo", 3))

    changelog_cfg = signals_cfg.get("changelog", {})
    changelog_enabled = changelog_cfg.get("enabled", True)
    changelog_files: list[str] = list(changelog_cfg.get("files", ["CHANGELOG.md"]))

    readme_enabled = signals_cfg.get("readme", {}).get("enabled", True)

    debug_log(f"[github-watch] START repos={repos}", log_file=ctx.debug_log_path)

    all_records: list[SignalRecord] = []
    repo_summaries: list[dict] = []

    for full_repo in repos:
        if "/" not in full_repo:
            ctx.warnings.append(f"invalid repo format (skipping): {full_repo}")
            continue
        owner, repo = full_repo.split("/", 1)

        debug_log(f"[github-watch] --- {full_repo} ---", log_file=ctx.debug_log_path)
        repo_records: list[SignalRecord] = []

        if release_enabled:
            repo_records += _collect_releases_for_repo(ctx, owner, repo, lookback_days, max_per_repo)

        if changelog_enabled:
            repo_records += _collect_changelog_for_repo(ctx, owner, repo, changelog_files)

        if readme_enabled:
            repo_records += _collect_readme_for_repo(ctx, owner, repo)

        all_records.extend(repo_records)

        signal_types = sorted(set(r.signal_type for r in repo_records))
        repo_summaries.append({
            "repo": full_repo,
            "signals": len(repo_records),
            "types": signal_types,
        })
        debug_log(f"[github-watch] repo {full_repo}: {len(repo_records)} signals", log_file=ctx.debug_log_path)

    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    signal_types_count: dict[str, int] = {}
    for r in all_records:
        signal_types_count[r.signal_type] = signal_types_count.get(r.signal_type, 0) + 1

    # Determine status
    if all_records:
        status = RunStatus.SUCCESS
    elif ctx.errors:
        status = RunStatus.FAILED
    else:
        status = RunStatus.EMPTY

    index_path = ctx.index_path
    run_json_path = ctx.run_json_path

    result = RunResult(
        lane="github-watch",
        date=ctx.date,
        status=status,
        started_at=started_at,
        session_id=None,
        finished_at=finished_at,
        warnings=ctx.warnings,
        errors=ctx.errors,
        signal_records=all_records,
        repos_checked=len(repos),
        signals_written=len(all_records),
        signal_types_count=signal_types_count,
        index_file=str(index_path),
    )

    # Write artifacts
    index_ok = _write_index_to_file(result, index_path)
    if ctx.errors or not index_ok:
        result.status = RunStatus.FAILED

    debug_log(f"[github-watch] RUNJSON WRITE status={result.status.value}", log_file=ctx.debug_log_path)
    _write_manifest_to_file(result, run_json_path)

    debug_log(f"[github-watch] END signals={len(all_records)} repos={len(repos)}", log_file=ctx.debug_log_path)
    return result


def _write_index_to_file(result: RunResult, index_path: Path) -> bool:
    """Write index.md from RunResult. Returns True on success."""
    try:
        write_index(result, index_path)
        return True
    except Exception as e:
        result.errors.append(f"failed to write index.md: {e}")
        return False


def _write_manifest_to_file(result: RunResult, run_json_path: Path) -> bool:
    """Write run.json from RunResult. Returns True on success."""
    try:
        write_run_manifest(result, run_json_path)
        return True
    except Exception as e:
        result.errors.append(f"failed to write run.json: {e}")
        return False


register_lane("github-watch", collect_github_watch)
