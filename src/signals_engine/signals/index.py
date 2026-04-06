"""Index.md writer."""
from pathlib import Path
from ..core import RunResult
from .render import render_index_markdown


def write_index(result: RunResult, path: Path) -> None:
    """Render and atomically write index.md from RunResult.

    Args:
        result: The RunResult to render.
        path: Destination path for index.md. Passed to render_index_markdown
            so it can compute relative links to signal files.
    """
    content = render_index_markdown(result, index_path=path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(path)
