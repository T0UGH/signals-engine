"""rize-watch lane collector."""
from __future__ import annotations

from datetime import datetime, timezone
import re

from ..core import RunContext, RunResult, RunStatus, SignalRecord
from ..sources.rize import fetch_ai_tools, RizeError, RizeTool
from ..signals.writer import write_signal
from ..signals.index import write_index
from ..runtime.run_manifest import write_run_manifest
from .registry import register_lane

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "rize-tool"

def _build_signal(ctx: RunContext, tool: RizeTool) -> SignalRecord:
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    filename = f"{tool.position:02d}-{_slug(tool.repo_slug)}__rize_ai_tools_rank__{ctx.date}.md"
    return SignalRecord(
        lane="rize-watch", signal_type="rize_ai_tools_rank", source="rize", entity_type="github_repo",
        entity_id=tool.repo_slug, title=f"#{tool.position} {tool.name} — Rize AI tools weekly ranking",
        source_url=tool.repo_url, fetched_at=fetched_at, file_path=str(ctx.signals_dir / filename),
        position=tool.position, text_preview=tool.description, external_url="https://rize.io/ai-tools",
    )

def collect_rize_watch(ctx: RunContext) -> RunResult:
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    lane_config = ctx.config.get("lanes", {}).get("rize-watch", {})
    max_items = int(lane_config.get("max_items", 20) or 20)
    result = RunResult(lane="rize-watch", date=ctx.date, status=RunStatus.SUCCESS, started_at=started_at)
    ctx.signals_dir.mkdir(parents=True, exist_ok=True)
    try:
        tools = fetch_ai_tools(url=lane_config.get("url", "https://rize.io/ai-tools"), timeout=int(lane_config.get("timeout", 20) or 20))
    except RizeError as exc:
        result.status = RunStatus.FAILED
        result.errors.append(str(exc))
        result.finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
        write_run_manifest(result, ctx.data_dir / "signals" / ctx.lane / ctx.date / "run.json")
        return result
    for tool in tools[:max_items]:
        record = _build_signal(ctx, tool)
        write_signal(record)
        result.signal_records.append(record)
    result.signals_written = len(result.signal_records)
    result.signal_types_count = {"rize_ai_tools_rank": result.signals_written} if result.signals_written else {}
    if not result.signal_records:
        result.status = RunStatus.EMPTY
        result.warnings.append("Rize ranking returned no usable GitHub tools")
    index_path = ctx.data_dir / "signals" / ctx.lane / ctx.date / "index.md"
    write_index(result, index_path)
    result.index_file = str(index_path)
    result.finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    write_run_manifest(result, ctx.data_dir / "signals" / ctx.lane / ctx.date / "run.json")
    return result

register_lane("rize-watch", collect_rize_watch)
