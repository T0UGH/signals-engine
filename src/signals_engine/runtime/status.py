"""Status command: read run status from existing artifacts."""
import json
from pathlib import Path

from ..core.defaults import resolve_data_dir


def get_run_status(
    lane: str,
    run_date: str,
    data_dir: Path | None = None,
) -> dict:
    """Read status for a lane/date run from existing run.json and artifacts.

    Args:
        lane: Lane name.
        run_date: Run date in YYYY-MM-DD format.
        data_dir: Override data directory.
    """
    if data_dir is None:
        data_dir = resolve_data_dir()

    run_json = data_dir / "signals" / lane / run_date / "run.json"
    index_md = data_dir / "signals" / lane / run_date / "index.md"

    result: dict = {
        "lane": lane,
        "date": run_date,
        "has_run": run_json.exists(),
        "run_file": None,
        "index_exists": index_md.exists(),
        "signals_written": 0,
    }

    if run_json.exists():
        try:
            rel = run_json.relative_to(data_dir)
            result["run_file"] = str(rel)
        except ValueError:
            result["run_file"] = str(run_json)

        try:
            with open(run_json) as f:
                data = json.load(f)
            result["status"] = data.get("status")
            result["signals_written"] = data.get("summary", {}).get("signals_written", 0)
            result["warnings"] = data.get("warnings", [])
            result["errors"] = data.get("errors", [])
        except Exception:
            result["status"] = "error"

    return result
