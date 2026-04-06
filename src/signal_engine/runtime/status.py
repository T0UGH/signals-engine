"""Status command: read run status from existing artifacts."""
import json
import os
from pathlib import Path


def get_run_status(lane: str, run_date: str) -> dict:
    """Read status for a lane/date run from existing run.json and artifacts."""
    data_dir = Path(os.environ.get(
        "DAILY_LANE_DATA_DIR",
        str(Path.home() / ".daily-lane-data")
    ))
    run_json = data_dir / "signals" / lane / run_date / "run.json"
    index_md = data_dir / "signals" / lane / run_date / "index.md"

    result = {
        "lane": lane,
        "date": run_date,
        "has_run": run_json.exists(),
        "run_file": str(run_json.relative_to(data_dir)) if run_json.exists() else None,
        "index_exists": index_md.exists(),
        "signals_written": 0,
    }

    if run_json.exists():
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
