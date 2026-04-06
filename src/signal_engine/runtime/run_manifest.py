"""Run manifest mapper and writer.

run.json is NOT a direct serialization of RunResult.
It is a stable external protocol rendered via this mapper only.
"""
import json
from pathlib import Path
from ..core import RunResult


def render_run_manifest(result: RunResult) -> dict:
    """Map RunResult to run.json protocol dict.

    This is the ONLY entry point from RunResult -> run.json.
    Signal records are NOT dumped in full; only file_paths are listed.
    """
    return {
        "lane": result.lane,
        "date": result.date,
        "status": result.status.value,
        "started_at": result.started_at,
        "finished_at": result.finished_at or "",
        "warnings": result.warnings,
        "errors": result.errors,
        "summary": {
            "repos_checked": result.repos_checked,
            "signals_written": result.signals_written,
            "signal_types": result.signal_types_count,
        },
        "artifacts": {
            "index_file": result.index_file or "",
            "signal_files": [r.file_path for r in result.signal_records if r.file_path],
        },
    }


def write_run_manifest(result: RunResult, path: Path) -> None:
    """Render and atomically write run.json."""
    manifest = render_run_manifest(result)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    tmp.rename(path)
