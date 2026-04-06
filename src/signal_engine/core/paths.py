"""Path construction utilities for Signal Engine."""
from pathlib import Path


def signal_file_path(lane: str, date: str, filename: str) -> Path:
    """Return the full path to a signal file under a lane/date/signals/ directory."""
    return Path("signals") / lane / date / "signals" / filename


def index_file_path(lane: str, date: str) -> Path:
    """Return the full path to an index.md under a lane/date/ directory."""
    return Path("signals") / lane / date / "index.md"


def run_json_path(lane: str, date: str) -> Path:
    """Return the full path to a run.json under a lane/date/ directory."""
    return Path("signals") / lane / date / "run.json"


def state_file_path(lane: str, owner: str, repo: str, file_type: str) -> Path:
    """Return the full path to a state file."""
    safe_owner = owner.replace("/", "__")
    safe_repo = repo.replace("/", "__")
    return Path("signals") / lane / "state" / f"{safe_owner}__{safe_repo}__{file_type}.md"
