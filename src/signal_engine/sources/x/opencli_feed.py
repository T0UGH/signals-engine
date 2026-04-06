"""OpenCLI-based X feed source."""
import json
import subprocess
from pathlib import Path
from typing import Any
from ...core.errors import SourceError


OPENCLI_WORKSPACE = "~/.openclaw/workspace/github/opencli"


def fetch_opencli_feed(
    opencli_path: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch X home timeline via opencli.

    Args:
        opencli_path: Path to opencli workspace (default: ~/.openclaw/workspace/github/opencli)
        limit: Number of tweets to fetch (default: 100)

    Returns:
        List of tweet dicts with keys: id, author, text, likes, retweets,
        replies, views, created_at, url

    Raises:
        SourceError: If opencli invocation fails or output is not valid JSON.
    """
    workspace = Path(opencli_path or OPENCLI_WORKSPACE).expanduser()
    main_js = workspace / "dist" / "main.js"

    if not main_js.exists():
        raise SourceError(f"opencli not found at {main_js} (workspace: {workspace})")

    cmd = [
        "node",
        str(main_js),
        "twitter",
        "timeline",
        "--limit",
        str(limit),
        "-f",
        "json",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise SourceError("opencli timeline timed out after 120s")
    except FileNotFoundError:
        raise SourceError(f"node not found (required to run opencli)")

    if result.returncode != 0:
        raise SourceError(f"opencli returned {result.returncode}: {result.stderr[:500]}")

    # Re-serialize via python to handle any non-standard JSON (emoji, control chars)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise SourceError(f"opencli output is not valid JSON: {e}")

    if data is None:
        return []
    if isinstance(data, list):
        return data
    raise SourceError(f"opencli returned unexpected type: {type(data).__name__}")
