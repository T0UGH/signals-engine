"""Run manifest mapper and writer.

run.json is NOT a direct serialization of RunResult.
It is a stable external protocol rendered via this mapper only.
"""
import json
from pathlib import Path
from ..core import RunResult


def _relative(path: str, base: Path) -> str:
    """Return path relative to base, or just the filename if not subpath."""
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(base.resolve()))
    except ValueError:
        return Path(path).name


def render_run_manifest(result: RunResult, run_json_path: Path | None = None) -> dict:
    """Map RunResult to run.json protocol dict.

    This is the ONLY entry point from RunResult -> run.json.
    Signal records are NOT dumped in full; only file_paths are listed.

    Args:
        result: The RunResult to map.
        run_json_path: Path to run.json being written. Used to compute relative
            paths for signal_files and index_file for portability.
    """
    if run_json_path is not None:
        base = run_json_path.parent
        index_rel = _relative(result.index_file or "", base) if result.index_file else ""
        signal_files = [
            _relative(r.file_path, base)
            for r in result.signal_records
            if r.file_path
        ]
    else:
        index_rel = result.index_file or ""
        signal_files = [r.file_path for r in result.signal_records if r.file_path]

    manifest = {
        "lane": result.lane,
        "date": result.date,
        "status": result.status.value,
        "started_at": result.started_at,
        "finished_at": result.finished_at or "",
        "session_id": result.session_id or "",
        "warnings": result.warnings,
        "errors": result.errors,
        "summary": {
            "repos_checked": result.repos_checked,
            "signals_written": result.signals_written,
            "signal_types": result.signal_types_count,
        },
        "artifacts": {
            "index_file": index_rel,
            "signal_files": signal_files,
        },
    }
    return manifest


def write_run_manifest(result: RunResult, path: Path) -> None:
    """Render and atomically write run.json.

    Args:
        result: The RunResult to write.
        path: Destination path for run.json. Used to compute relative paths.
    """
    manifest = render_run_manifest(result, run_json_path=path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    tmp.rename(path)
