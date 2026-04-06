"""Index.md writer."""
from pathlib import Path
from ..core import RunResult
from .render import render_index_markdown


def write_index(result: RunResult, path: Path) -> None:
    """Render and atomically write index.md from RunResult."""
    content = render_index_markdown(result)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(path)
