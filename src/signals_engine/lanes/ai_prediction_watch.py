"""ai-prediction-watch lane collector."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..core import RunContext, RunResult, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..runtime.run_manifest import write_run_manifest
from ..signals.index import write_index
from ..signals.writer import write_signal
from ..sources.polymarket import PolymarketError, PolymarketMarket, fetch_polymarket_markets
from .registry import register_lane


DEFAULT_QUERY_SPECS = (
    {"topic": "model-race", "query": "best AI model"},
    {"topic": "coding-ai", "query": "coding AI"},
    {"topic": "benchmark", "query": "AI benchmark"},
    {"topic": "company-expectation", "query": "OpenAI Anthropic Google"},
)
WORKFLOW_DETAIL_TERMS = (
    "tutorial",
    "workflow",
    "prompt",
    "setup",
    "install",
    "how to",
    "orchestration",
)


@dataclass(frozen=True)
class QuerySpec:
    topic: str
    query: str


def _parse_positive_int(value: object, *, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ai-prediction-watch '{field_name}' must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"ai-prediction-watch '{field_name}' must be a positive integer")
    return parsed


def _normalize_query_specs(raw_specs: object) -> list[QuerySpec]:
    if not raw_specs:
        return [QuerySpec(**spec) for spec in DEFAULT_QUERY_SPECS]

    specs: list[QuerySpec] = []
    if not isinstance(raw_specs, list):
        return [QuerySpec(**spec) for spec in DEFAULT_QUERY_SPECS]

    for raw_spec in raw_specs:
        if isinstance(raw_spec, str) and raw_spec.strip():
            specs.append(QuerySpec(topic="custom", query=raw_spec.strip()))
            continue
        if not isinstance(raw_spec, dict):
            continue
        query = str(raw_spec.get("query") or raw_spec.get("q") or "").strip()
        if not query:
            continue
        topic = str(raw_spec.get("topic") or raw_spec.get("group") or "custom").strip() or "custom"
        specs.append(QuerySpec(topic=topic, query=query))

    return specs or [QuerySpec(**spec) for spec in DEFAULT_QUERY_SPECS]


def _format_compact_metric(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _build_summary(market: PolymarketMarket) -> str:
    outcomes = ", ".join(f"{name} {probability * 100:.1f}%" for name, probability in market.top_outcomes)
    parts = [f"Market expectation: {market.primary_outcome} {market.primary_probability * 100:.1f}%."]
    if outcomes:
        parts.append(f"Top outcomes: {outcomes}.")
    if market.volume_30d:
        parts.append(f"30d volume {_format_compact_metric(market.volume_30d)}.")
    if market.liquidity:
        parts.append(f"Liquidity {_format_compact_metric(market.liquidity)}.")
    return " ".join(parts)


def _looks_like_workflow_detail(market: PolymarketMarket) -> bool:
    haystack = " ".join(
        [
            market.event_title.lower(),
            market.question.lower(),
            " ".join(name.lower() for name, _ in market.top_outcomes),
        ]
    )
    return any(term in haystack for term in WORKFLOW_DETAIL_TERMS)


def _build_signal(ctx: RunContext, spec: QuerySpec, market: PolymarketMarket) -> SignalRecord:
    filename = f"pm__{spec.topic}__{market.event_id}__prediction_market__{ctx.date}.md"
    file_path = str(ctx.signals_dir / filename)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    record = SignalRecord(
        lane="ai-prediction-watch",
        signal_type="prediction_market",
        source="polymarket",
        entity_type="event",
        entity_id=market.event_id,
        title=market.question,
        source_url=market.url,
        fetched_at=fetched_at,
        file_path=file_path,
        text_preview=_build_summary(market),
        group=spec.topic,
        query=spec.query,
        event_title=market.event_title,
        primary_outcome=market.primary_outcome,
        primary_probability=market.primary_probability,
        outcome_probabilities=[
            {"name": name, "probability": probability}
            for name, probability in market.top_outcomes
        ],
        volume_24h=market.volume_24h,
        volume_30d=market.volume_30d,
        liquidity=market.liquidity,
        price_movement=market.price_movement,
        end_date=market.end_date,
    )
    write_signal(record)
    return record


def collect_ai_prediction_watch(ctx: RunContext) -> RunResult:
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    lane_config = ctx.config.get("lanes", {}).get("ai-prediction-watch", {})
    source_config = lane_config.get("source", {})

    try:
        max_pages = _parse_positive_int(source_config.get("max_pages", 2), field_name="source.max_pages")
        timeout = _parse_positive_int(source_config.get("timeout", 15), field_name="source.timeout")
        max_per_query = _parse_positive_int(lane_config.get("max_per_query", 3), field_name="max_per_query")
    except ValueError as exc:
        ctx.errors.append(str(exc))
        return _finalize(ctx, started_at, [], 0)

    query_specs = _normalize_query_specs(lane_config.get("queries"))

    ctx.ensure_dirs()
    records: list[SignalRecord] = []
    seen_event_ids: set[str] = set()
    queries_checked = 0

    for spec in query_specs:
        queries_checked += 1
        debug_log(f"[ai-prediction-watch] query={spec.query} topic={spec.topic}", log_file=ctx.debug_log_path)
        try:
            candidates = fetch_polymarket_markets(
                spec.query,
                max_pages=max_pages,
                timeout=timeout,
                max_results=max_per_query * 3,
            )
        except PolymarketError as exc:
            debug_log(
                f"[ai-prediction-watch] query failed: {spec.query}: {exc}",
                log_file=ctx.debug_log_path,
            )
            ctx.errors.append(f"query '{spec.query}' failed: {exc}")
            continue

        written_for_query = 0
        for market in candidates:
            if market.event_id in seen_event_ids:
                continue
            if _looks_like_workflow_detail(market):
                debug_log(
                    f"[ai-prediction-watch] skip workflow-detail market {market.event_id}",
                    log_file=ctx.debug_log_path,
                )
                continue
            seen_event_ids.add(market.event_id)
            try:
                record = _build_signal(ctx, spec, market)
                records.append(record)
                written_for_query += 1
            except Exception as exc:
                debug_log(
                    f"[ai-prediction-watch] failed to write market {market.event_id}: {exc}",
                    log_file=ctx.debug_log_path,
                )
                ctx.errors.append(f"failed to write market {market.event_id}: {exc}")
            if written_for_query >= max_per_query:
                break

    return _finalize(ctx, started_at, records, queries_checked)


def _finalize(ctx: RunContext, started_at: str, records: list[SignalRecord], queries_checked: int) -> RunResult:
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    signal_types_count: dict[str, int] = {}
    for record in records:
        signal_types_count[record.signal_type] = signal_types_count.get(record.signal_type, 0) + 1

    status = RunStatus.SUCCESS if records else RunStatus.EMPTY
    if ctx.errors:
        status = RunStatus.FAILED

    result = RunResult(
        lane="ai-prediction-watch",
        date=ctx.date,
        status=status,
        started_at=started_at,
        session_id=None,
        finished_at=finished_at,
        warnings=ctx.warnings,
        errors=ctx.errors,
        signal_records=records,
        repos_checked=queries_checked,
        signals_written=len(records),
        signal_types_count=signal_types_count,
        index_file=str(ctx.index_path),
    )
    _write_index_to_file(result, ctx.index_path)
    _write_manifest_to_file(result, ctx.run_json_path)
    return result


def _write_index_to_file(result: RunResult, index_path: Path) -> bool:
    try:
        write_index(result, index_path)
        return True
    except Exception as exc:
        result.errors.append(f"failed to write index.md: {exc}")
        result.status = RunStatus.FAILED
        return False


def _write_manifest_to_file(result: RunResult, run_json_path: Path) -> bool:
    try:
        write_run_manifest(result, run_json_path)
        return True
    except Exception as exc:
        result.errors.append(f"failed to write run.json: {exc}")
        result.status = RunStatus.FAILED
        return False


register_lane("ai-prediction-watch", collect_ai_prediction_watch)
