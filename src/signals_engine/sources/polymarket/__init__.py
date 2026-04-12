"""Polymarket public Gamma search source for prediction-market lanes."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from urllib.parse import urlencode

import httpx


GAMMA_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
USER_AGENT = "signals-engine/0.2 polymarket"
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "be",
    "by",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "who",
    "will",
}


@dataclass(frozen=True)
class PolymarketMarket:
    event_id: str
    market_id: str
    event_title: str
    question: str
    url: str
    primary_outcome: str
    primary_probability: float
    top_outcomes: list[tuple[str, float]]
    volume_24h: float
    volume_30d: float
    liquidity: float
    price_movement: str
    end_date: str
    updated_at: str
    relevance: float


class PolymarketError(RuntimeError):
    """Raised when Polymarket search retrieval fails."""


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", value.lower()).split())


def _query_tokens(value: str) -> set[str]:
    tokens = []
    for token in _normalize_text(value).split():
        if len(token) <= 1:
            continue
        if token in _STOP_WORDS:
            continue
        tokens.append(token)
    return set(tokens)


def _date_only(value: object) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _parse_json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _parse_outcome_probabilities(market: dict[str, Any]) -> list[tuple[str, float]]:
    outcomes = _parse_json_list(market.get("outcomes"))
    prices = _parse_json_list(market.get("outcomePrices"))
    parsed: list[tuple[str, float]] = []
    for index, price in enumerate(prices):
        probability = _safe_float(price, default=-1.0)
        if probability < 0:
            continue
        name = str(outcomes[index]) if index < len(outcomes) else f"Outcome {index + 1}"
        parsed.append((name, probability))
    return parsed


def _shorten_question(question: str) -> str:
    text = question.strip().rstrip("?")
    match = re.match(
        r"^Will\s+(.+?)\s+(?:win|be|make|reach|have|lose|qualify|advance|get|become|remain|stay)\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return text


def _format_price_movement(market: dict[str, Any]) -> str:
    changes = [
        ("today", _safe_float(market.get("oneDayPriceChange"))),
        ("this week", _safe_float(market.get("oneWeekPriceChange"))),
        ("this month", _safe_float(market.get("oneMonthPriceChange"))),
    ]
    period, raw_change = max(changes, key=lambda pair: abs(pair[1]))
    if abs(raw_change) < 0.01:
        return ""
    direction = "up" if raw_change > 0 else "down"
    return f"{direction} {abs(raw_change) * 100:.1f}% {period}"


def _compute_relevance(query: str, event_title: str, question: str, outcome_names: list[str]) -> float:
    query_norm = _normalize_text(query)
    if not query_norm:
        return 0.0
    query_terms = _query_tokens(query)
    if not query_terms:
        return 0.0

    candidates = [event_title, question, *outcome_names]
    best = 0.0
    for candidate in candidates:
        candidate_norm = _normalize_text(candidate)
        if not candidate_norm:
            continue
        if query_norm in candidate_norm:
            best = max(best, 1.0)
            continue
        candidate_terms = _query_tokens(candidate)
        overlap = len(query_terms & candidate_terms)
        if overlap == 0:
            continue
        best = max(best, overlap / len(query_terms))
    return round(best, 2)


def _derive_top_outcomes(active_markets: list[dict[str, Any]]) -> list[tuple[str, float]]:
    if not active_markets:
        return []

    top_market = active_markets[0]
    outcome_prices = _parse_outcome_probabilities(top_market)
    binary_top_market = (
        len(outcome_prices) == 2
        and {name.lower() for name, _ in outcome_prices} == {"yes", "no"}
    )

    if binary_top_market and len(active_markets) > 1:
        synthesized: list[tuple[str, float]] = []
        for market in active_markets:
            yes_probability = None
            for name, probability in _parse_outcome_probabilities(market):
                if name.lower() == "yes":
                    yes_probability = probability
                    break
            question = str(market.get("question") or "").strip()
            if not question or yes_probability is None:
                continue
            synthesized.append((_shorten_question(question), yes_probability))
        if synthesized:
            synthesized.sort(key=lambda pair: pair[1], reverse=True)
            return synthesized[:3]

    outcome_prices.sort(key=lambda pair: pair[1], reverse=True)
    return outcome_prices[:3]


def parse_polymarket_search_response(
    payload: dict[str, Any],
    query: str,
    *,
    max_results: int = 10,
    min_relevance: float = 0.2,
) -> list[PolymarketMarket]:
    """Parse a Polymarket search payload into normalized market signals."""
    events = payload.get("events", [])
    if not isinstance(events, list):
        return []

    markets: list[PolymarketMarket] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("closed", False) or not event.get("active", True):
            continue

        event_title = str(event.get("title") or "").strip()
        if not event_title:
            continue

        active_markets: list[dict[str, Any]] = []
        for market in event.get("markets") or []:
            if not isinstance(market, dict):
                continue
            if market.get("closed", False) or not market.get("active", True):
                continue
            if _safe_float(market.get("liquidity")) <= 0:
                continue
            if not _parse_outcome_probabilities(market):
                continue
            active_markets.append(market)

        if not active_markets:
            continue

        active_markets.sort(
            key=lambda market: (
                _safe_float(market.get("volume")),
                _safe_float(market.get("liquidity")),
            ),
            reverse=True,
        )
        top_market = active_markets[0]
        question = str(top_market.get("question") or event_title).strip() or event_title
        top_outcomes = _derive_top_outcomes(active_markets)
        if not top_outcomes:
            continue

        primary_outcome, primary_probability = top_outcomes[0]
        relevance = _compute_relevance(
            query,
            event_title,
            question,
            [name for name, _ in top_outcomes],
        )
        if relevance < min_relevance:
            continue

        slug = str(event.get("slug") or "").strip()
        event_id = str(event.get("id") or "").strip()
        markets.append(
            PolymarketMarket(
                event_id=event_id,
                market_id=str(top_market.get("id") or "").strip(),
                event_title=event_title,
                question=question,
                url=f"https://polymarket.com/event/{slug or event_id}",
                primary_outcome=primary_outcome,
                primary_probability=primary_probability,
                top_outcomes=top_outcomes,
                volume_24h=_safe_float(event.get("volume24hr")) or _safe_float(top_market.get("volume24hr")),
                volume_30d=_safe_float(event.get("volume1mo")) or _safe_float(top_market.get("volume")),
                liquidity=_safe_float(event.get("liquidity")) or _safe_float(top_market.get("liquidity")),
                price_movement=_format_price_movement(top_market),
                end_date=_date_only(top_market.get("endDate") or event.get("endDate")),
                updated_at=str(event.get("updatedAt") or "").strip(),
                relevance=relevance,
            )
        )

    markets.sort(
        key=lambda market: (
            market.relevance,
            market.volume_30d,
            market.liquidity,
            market.updated_at,
        ),
        reverse=True,
    )
    return markets[:max_results]


def _fetch_search_page(query: str, *, page: int, timeout: int) -> dict[str, Any]:
    params = {
        "q": query,
        "page": str(page),
        "events_status": "active",
        "keep_closed_markets": "0",
    }
    url = f"{GAMMA_SEARCH_URL}?{urlencode(params)}"

    try:
        with httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            transport=httpx.HTTPTransport(retries=1),
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        raise PolymarketError(f"request failed for {query!r}: {exc}") from exc

    if response.status_code >= 400:
        raise PolymarketError(f"HTTP {response.status_code} for {query!r}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise PolymarketError(f"invalid JSON for {query!r}") from exc
    if not isinstance(payload, dict):
        raise PolymarketError(f"unexpected payload for {query!r}")
    return payload


def fetch_polymarket_markets(
    query: str,
    *,
    max_pages: int = 2,
    timeout: int = 15,
    max_results: int = 10,
    min_relevance: float = 0.2,
) -> list[PolymarketMarket]:
    """Fetch and normalize Polymarket search results for a query."""
    deduped: dict[str, PolymarketMarket] = {}
    page_count = max(1, int(max_pages))
    for page in range(1, page_count + 1):
        payload = _fetch_search_page(query, page=page, timeout=timeout)
        for market in parse_polymarket_search_response(
            payload,
            query,
            max_results=max_results * 2,
            min_relevance=min_relevance,
        ):
            existing = deduped.get(market.event_id)
            if existing is None or market.relevance > existing.relevance:
                deduped[market.event_id] = market

    markets = list(deduped.values())
    markets.sort(
        key=lambda market: (
            market.relevance,
            market.volume_30d,
            market.liquidity,
            market.updated_at,
        ),
        reverse=True,
    )
    return markets[:max_results]


__all__ = [
    "PolymarketError",
    "PolymarketMarket",
    "fetch_polymarket_markets",
    "parse_polymarket_search_response",
]
