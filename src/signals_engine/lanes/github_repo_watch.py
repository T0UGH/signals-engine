"""Reusable GitHub repo-watch collectors.

Shared by the legacy multi-repo ``github-watch`` lane and the new
repo-specific GitHub watch lanes.
"""
from datetime import datetime, timezone
from pathlib import Path

from ..core import RunContext, RunResult, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..runtime.run_manifest import write_run_manifest
from ..signals.index import write_index
from ..signals.writer import write_signal
from ..sources.github import diff_content, fetch_content, fetch_releases
from ..sources.github.releases import GhError

_MAX_CONTENT_SIZE = 102400


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


def _parse_repo(full_repo: str) -> tuple[str, str] | None:
    """Parse ``owner/repo`` and reject invalid shapes."""
    if not isinstance(full_repo, str):
        return None
    normalized = full_repo.strip()
    if normalized.count("/") != 1:
        return None
    owner, repo = normalized.split("/", 1)
    if not owner or not repo:
        return None
    return owner, repo


def _state_path(
    state_dir: Path,
    owner: str,
    repo: str,
    signal_type: str,
    content_path: str = "",
) -> Path:
    """Return the lane-local state path for a repo and signal target."""
    parts = [owner, repo, signal_type]
    if content_path:
        parts.append(content_path)
    safe_parts = [_safe_filename(part) for part in parts]
    return state_dir / f"{'__'.join(safe_parts)}.md"


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
    lane_name: str,
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

    record = SignalRecord(
        lane=lane_name,
        signal_type="release",
        source="github",
        entity_type="repo",
        entity_id=f"{owner}/{repo}",
        title=name or tag,
        source_url=html_url,
        fetched_at=fetched_at,
        file_path=file_path,
        session_id="",
        handle=f"{owner}/{repo}",
        post_id=tag,
        created_at=published_at,
        prerelease=prerelease,
        release_assets=assets,
        release_body=body or "(no release notes)",
    )
    write_signal(record)
    return record


def _build_changelog_signal(
    ctx: RunContext,
    lane_name: str,
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

    record = SignalRecord(
        lane=lane_name,
        signal_type="changelog",
        source="github",
        entity_type="repo",
        entity_id=f"{owner}/{repo}",
        title=f"{repo} CHANGELOG updated",
        source_url=f"https://github.com/{owner}/{repo}/blob/HEAD/{changelog_path}",
        fetched_at=fetched_at,
        file_path=file_path,
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
    lane_name: str,
    owner: str,
    repo: str,
    readme_path: str,
    diff_text: str,
    stats: str,
) -> SignalRecord:
    """Build and write a README change signal."""
    filename = f"{owner}__{repo}__readme__{ctx.date}.md"
    file_path = str(ctx.signals_dir / filename)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    record = SignalRecord(
        lane=lane_name,
        signal_type="readme",
        source="github",
        entity_type="repo",
        entity_id=f"{owner}/{repo}",
        title=f"{repo} README updated",
        source_url=f"https://github.com/{owner}/{repo}/blob/HEAD/{readme_path}",
        fetched_at=fetched_at,
        file_path=file_path,
        session_id="",
        handle=f"{owner}/{repo}",
        post_id=readme_path,
        created_at="",
        diff_stats=stats,
        diff_text=diff_text,
    )
    write_signal(record)
    return record


def _write_index_to_file(result: RunResult, index_path: Path) -> bool:
    """Write index.md from RunResult. Returns True on success."""
    try:
        write_index(result, index_path)
        return True
    except Exception as exc:
        result.errors.append(f"failed to write index.md: {exc}")
        return False


def _write_manifest_to_file(result: RunResult, run_json_path: Path) -> bool:
    """Write run.json from RunResult. Returns True on success."""
    try:
        write_run_manifest(result, run_json_path)
        return True
    except Exception as exc:
        result.errors.append(f"failed to write run.json: {exc}")
        return False


def _signal_settings(signals_cfg: dict) -> dict:
    """Resolve GitHub repo-watch settings from lane config."""
    release_cfg = signals_cfg.get("release", {})
    changelog_cfg = signals_cfg.get("changelog", {})
    readme_cfg = signals_cfg.get("readme", {})

    return {
        "release_enabled": release_cfg.get("enabled", True),
        "lookback_days": int(release_cfg.get("lookback_days", 7)),
        "max_per_repo": int(release_cfg.get("max_per_repo", 3)),
        "changelog_enabled": changelog_cfg.get("enabled", True),
        "changelog_files": list(changelog_cfg.get("files", ["CHANGELOG.md"])),
        "readme_enabled": readme_cfg.get("enabled", True),
    }


def _collect_releases_for_repo(
    ctx: RunContext,
    lane_name: str,
    owner: str,
    repo: str,
    lookback_days: int,
    max_per_repo: int,
) -> list[SignalRecord]:
    """Collect release signals for one repo."""
    records: list[SignalRecord] = []
    try:
        releases = fetch_releases(owner, repo, lookback_days, max_per_repo)
    except GhError as exc:
        debug_log(f"[{lane_name}] {owner}/{repo} releases GhError: {exc}", log_file=ctx.debug_log_path)
        ctx.warnings.append(f"{owner}/{repo} releases: {exc}")
        return []

    for rel in releases:
        try:
            record = _build_release_signal(
                ctx,
                lane_name,
                owner,
                repo,
                tag=rel.tag,
                name=rel.name,
                body=rel.body,
                html_url=rel.html_url,
                published_at=rel.published_at,
                prerelease=rel.prerelease,
                assets=rel.assets,
            )
            records.append(record)
            debug_log(f"[{lane_name}] + release: {owner}/{repo} {rel.tag}", log_file=ctx.debug_log_path)
        except Exception as exc:
            debug_log(
                f"[{lane_name}] failed to write release signal {owner}/{repo} {rel.tag}: {exc}",
                log_file=ctx.debug_log_path,
            )
            ctx.errors.append(f"failed to write release signal {rel.tag}: {exc}")
    return records


def _collect_changelog_for_repo(
    ctx: RunContext,
    lane_name: str,
    owner: str,
    repo: str,
    changelog_files: list[str],
) -> list[SignalRecord]:
    """Collect changelog change signals for one repo."""
    records: list[SignalRecord] = []

    for changelog_path in changelog_files:
        try:
            result = fetch_content(owner, repo, changelog_path)
        except GhError as exc:
            debug_log(
                f"[{lane_name}] {owner}/{repo} changelog {changelog_path} GhError: {exc}",
                log_file=ctx.debug_log_path,
            )
            ctx.warnings.append(f"{owner}/{repo} changelog {changelog_path}: {exc}")
            continue

        if result is None:
            debug_log(f"[{lane_name}] . {owner}/{repo} changelog: not found", log_file=ctx.debug_log_path)
            continue

        content = _truncate(result.content)
        state_path = _state_path(ctx.state_dir, owner, repo, "changelog", result.path or changelog_path)
        old_content = _read_state(state_path)

        if old_content is None:
            _write_state(state_path, content)
            debug_log(f"[{lane_name}] ~ {owner}/{repo} changelog: first run, state saved", log_file=ctx.debug_log_path)
            return []

        diff_result = diff_content(old_content, content)
        if diff_result.is_first:
            _write_state(state_path, content)
            debug_log(f"[{lane_name}] ~ {owner}/{repo} changelog: first run, state saved", log_file=ctx.debug_log_path)
            return []

        if not diff_result.changed:
            debug_log(f"[{lane_name}] . {owner}/{repo} changelog: no change", log_file=ctx.debug_log_path)
            return []

        try:
            record = _build_changelog_signal(
                ctx,
                lane_name,
                owner,
                repo,
                result.path or changelog_path,
                diff_text=diff_result.diff_text,
                stats=diff_result.stats,
            )
            records.append(record)
            _write_state(state_path, content)
            debug_log(f"[{lane_name}] + {owner}/{repo} changelog: ({diff_result.stats})", log_file=ctx.debug_log_path)
        except Exception as exc:
            debug_log(
                f"[{lane_name}] failed to write changelog signal {owner}/{repo}: {exc}",
                log_file=ctx.debug_log_path,
            )
            ctx.errors.append(f"failed to write changelog signal: {exc}")
        return records

    return records


def _collect_readme_for_repo(
    ctx: RunContext,
    lane_name: str,
    owner: str,
    repo: str,
) -> list[SignalRecord]:
    """Collect README change signals for one repo."""
    records: list[SignalRecord] = []

    try:
        result = fetch_content(owner, repo, "README.md")
    except GhError as exc:
        debug_log(f"[{lane_name}] {owner}/{repo} README GhError: {exc}", log_file=ctx.debug_log_path)
        ctx.warnings.append(f"{owner}/{repo} README: {exc}")
        return []

    if result is None:
        debug_log(f"[{lane_name}] . {owner}/{repo} README: not found", log_file=ctx.debug_log_path)
        return []

    content = _truncate(result.content)
    readme_path = result.path or "README.md"
    state_path = _state_path(ctx.state_dir, owner, repo, "readme", readme_path)
    old_content = _read_state(state_path)

    if old_content is None:
        _write_state(state_path, content)
        debug_log(f"[{lane_name}] ~ {owner}/{repo} README: first run, state saved", log_file=ctx.debug_log_path)
        return []

    diff_result = diff_content(old_content, content)
    if not diff_result.changed:
        debug_log(f"[{lane_name}] . {owner}/{repo} README: no change", log_file=ctx.debug_log_path)
        return []

    try:
        record = _build_readme_signal(
            ctx,
            lane_name,
            owner,
            repo,
            readme_path=readme_path,
            diff_text=diff_result.diff_text,
            stats=diff_result.stats,
        )
        records.append(record)
        _write_state(state_path, content)
        debug_log(f"[{lane_name}] + {owner}/{repo} README: ({diff_result.stats})", log_file=ctx.debug_log_path)
    except Exception as exc:
        debug_log(f"[{lane_name}] failed to write readme signal {owner}/{repo}: {exc}", log_file=ctx.debug_log_path)
        ctx.errors.append(f"failed to write readme signal: {exc}")

    return records


def _collect_repo_records(
    ctx: RunContext,
    lane_name: str,
    owner: str,
    repo: str,
    settings: dict,
) -> list[SignalRecord]:
    """Collect all enabled GitHub repo-watch signals for a single repo."""
    records: list[SignalRecord] = []

    if settings["release_enabled"]:
        records.extend(
            _collect_releases_for_repo(
                ctx,
                lane_name,
                owner,
                repo,
                settings["lookback_days"],
                settings["max_per_repo"],
            )
        )

    if settings["changelog_enabled"]:
        records.extend(
            _collect_changelog_for_repo(
                ctx,
                lane_name,
                owner,
                repo,
                settings["changelog_files"],
            )
        )

    if settings["readme_enabled"]:
        records.extend(_collect_readme_for_repo(ctx, lane_name, owner, repo))

    return records


def _finalize_run(
    ctx: RunContext,
    lane_name: str,
    started_at: str,
    records: list[SignalRecord],
    repos_checked: int,
) -> RunResult:
    """Render and write run artifacts for a GitHub watch lane."""
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    signal_types_count: dict[str, int] = {}
    for record in records:
        signal_types_count[record.signal_type] = signal_types_count.get(record.signal_type, 0) + 1

    status = RunStatus.SUCCESS if records else RunStatus.EMPTY
    if ctx.errors:
        status = RunStatus.FAILED

    result = RunResult(
        lane=lane_name,
        date=ctx.date,
        status=status,
        started_at=started_at,
        session_id=None,
        finished_at=finished_at,
        warnings=ctx.warnings,
        errors=ctx.errors,
        signal_records=records,
        repos_checked=repos_checked,
        signals_written=len(records),
        signal_types_count=signal_types_count,
        index_file=str(ctx.index_path),
    )

    index_ok = _write_index_to_file(result, ctx.index_path)
    if ctx.errors or not index_ok:
        result.status = RunStatus.FAILED

    debug_log(f"[{lane_name}] RUNJSON WRITE status={result.status.value}", log_file=ctx.debug_log_path)
    manifest_ok = _write_manifest_to_file(result, ctx.run_json_path)
    if not manifest_ok:
        result.status = RunStatus.FAILED

    debug_log(f"[{lane_name}] END signals={len(records)} repos={repos_checked}", log_file=ctx.debug_log_path)
    return result


def collect_github_repos_watch(
    ctx: RunContext,
    lane_name: str,
    repos: list[str],
    signals_cfg: dict,
    invalid_repo_is_error: bool = False,
) -> RunResult:
    """Collect GitHub repo-watch signals for one or more repos."""
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    settings = _signal_settings(signals_cfg)
    debug_log(f"[{lane_name}] START repos={repos}", log_file=ctx.debug_log_path)

    all_records: list[SignalRecord] = []
    repos_checked = 0

    for full_repo in repos:
        parsed = _parse_repo(full_repo)
        if parsed is None:
            message = f"invalid repo format: {full_repo}"
            if invalid_repo_is_error:
                ctx.errors.append(message)
                break
            ctx.warnings.append(f"{message} (skipping)")
            continue

        owner, repo = parsed
        repos_checked += 1
        debug_log(f"[{lane_name}] --- {full_repo} ---", log_file=ctx.debug_log_path)

        repo_records = _collect_repo_records(ctx, lane_name, owner, repo, settings)
        all_records.extend(repo_records)
        debug_log(f"[{lane_name}] repo {full_repo}: {len(repo_records)} signals", log_file=ctx.debug_log_path)

    return _finalize_run(ctx, lane_name, started_at, all_records, repos_checked)


def collect_github_repo_watch(ctx: RunContext, lane_name: str | None = None) -> RunResult:
    """Collect GitHub repo-watch signals for a single repo-specific lane."""
    lane_name = lane_name or ctx.lane
    lane_config = ctx.config.get("lanes", {}).get(lane_name, {})
    repo = lane_config.get("repo")

    if not isinstance(repo, str) or not repo.strip():
        ctx.errors.append(f"{lane_name} requires a non-empty 'repo' config value")
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
        return _finalize_run(ctx, lane_name, started_at, [], 0)

    normalized_repo = repo.strip()
    if _parse_repo(normalized_repo) is None:
        ctx.errors.append(f"invalid repo format: {normalized_repo}")
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
        return _finalize_run(ctx, lane_name, started_at, [], 0)

    return collect_github_repos_watch(
        ctx,
        lane_name=lane_name,
        repos=[normalized_repo],
        signals_cfg=lane_config.get("signals", {}),
        invalid_repo_is_error=True,
    )
