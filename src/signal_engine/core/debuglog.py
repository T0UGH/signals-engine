"""Minimal debug logging helper.

Writes to stderr and optionally appends to a log file.
No log rotation, no structured JSON — just plain text lines.
"""
from pathlib import Path
import sys


def debug_log(message: str, log_file: Path | str | None = None) -> None:
    """Write a debug line to stderr and optionally append to a log file.

    Args:
        message: The debug message to log.
        log_file: Optional path to a file to append to. If None, only stderr.
    """
    line = f"[debug] {message}"
    print(line, file=sys.stderr)
    if log_file is not None:
        p = Path(log_file).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(line + "\n")
