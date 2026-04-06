"""Atomic signal markdown writer."""
from pathlib import Path
from ..core import SignalRecord
from .render import render_signal_markdown


def write_signal(record: SignalRecord) -> str:
    """Render and atomically write a SignalRecord to its file_path.

    Returns the file_path written.
    Raises WriteError on failure.
    """
    if not record.file_path:
        raise ValueError("record.file_path is required")

    path = Path(record.file_path)
    content = render_signal_markdown(record)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(path)
    return str(path)
