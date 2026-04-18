"""Hacker News Firebase and Algolia search source helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import json
import re
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


USER_AGENT = "signals-engine/0.1 hacker-news-watch"
HN_API_ROOT = "https://hacker-news.firebaseio.com/v0"
HN_SEARCH_API_ROOT = "https://hn.algolia.com/api/v1"
SEARCH_STORY_CONTEXT = "search:story"
SUPPORTED_STORY_LISTS = {
    "top": "topstories",
    "new": "newstories",
    "best": "beststories",
    "ask": "askstories",
    "show": "showstories",
}


@dataclass
class HackerNewsStory:
    story_id: int
    title: str
    discussion_url: str
    external_url: str
    author: str
    created_at: str
    score: int
    descendants: int
    position: int
    text_preview: str
    story_list_name: str
    top_comments: list[str] = field(default_factory=list)
    query: str = ""


class HackerNewsError(RuntimeError):
    """Raised when Hacker News retrieval fails."""


def validate_story_list(value: object) -> str:
    story_list = str(value or "top").strip().lower()
    if story_list not in SUPPORTED_STORY_LISTS:
        supported = ", ".join(sorted(SUPPORTED_STORY_LISTS))
        raise ValueError(f"hacker-news-watch 'story_list' must be one of: {supported}")
    return story_list


def clean_html_text(value: object) -> str:
    text = str(value or "").replace("\r", "")
    if not text:
        return ""

    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)<p\b[^>]*>", "", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)<div\b[^>]*>", "", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)<li\b[^>]*>", "- ", text)
    text = re.sub(r"(?is)<pre\b[^>]*>", "\n", text)
    text = re.sub(r"(?is)</pre\s*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    collapsed: list[str] = []
    blank_pending = False
    for line in lines:
        if not line:
            blank_pending = bool(collapsed)
            continue
        if blank_pending:
            collapsed.append("")
            blank_pending = False
        collapsed.append(line)
    return "\n".join(collapsed).strip()


def fetch_hackernews_stories(
    *,
    story_list: str = "top",
    max_stories: int = 10,
    fetch_top_comments: bool = True,
    max_top_comments: int = 3,
    timeout: int = 15,
) -> list[HackerNewsStory]:
    """Fetch Hacker News stories from the official Firebase API."""
    normalized_list = validate_story_list(story_list)
    endpoint_name = SUPPORTED_STORY_LISTS[normalized_list]
    ids = _request_json(f"{HN_API_ROOT}/{endpoint_name}.json", timeout=timeout)
    if not isinstance(ids, list):
        raise HackerNewsError(f"invalid list payload for {endpoint_name}")

    stories: list[HackerNewsStory] = []
    for position, raw_story_id in enumerate(ids[:max_stories], start=1):
        story = _fetch_story_by_id(
            raw_story_id,
            position=position,
            context_label=endpoint_name,
            fetch_top_comments=fetch_top_comments,
            max_top_comments=max_top_comments,
            timeout=timeout,
        )
        if story is not None:
            stories.append(story)
    return stories


def fetch_hackernews_search_stories(
    *,
    queries: list[str],
    max_hits_per_query: int = 5,
    fetch_top_comments: bool = True,
    max_top_comments: int = 3,
    timeout: int = 15,
) -> list[HackerNewsStory]:
    """Discover story hits via Algolia, then hydrate canonical story data from Firebase."""
    stories: list[HackerNewsStory] = []
    seen_story_ids: set[int] = set()
    position = 0

    for query in queries:
        for story_id in _search_story_ids(query, max_hits_per_query=max_hits_per_query, timeout=timeout):
            if story_id in seen_story_ids:
                continue
            story = _fetch_story_by_id(
                story_id,
                position=position + 1,
                context_label=SEARCH_STORY_CONTEXT,
                fetch_top_comments=fetch_top_comments,
                max_top_comments=max_top_comments,
                timeout=timeout,
                query=query,
            )
            if story is None:
                continue
            stories.append(story)
            seen_story_ids.add(story.story_id)
            position += 1

    return stories


def discussion_url(story_id: int) -> str:
    return f"https://news.ycombinator.com/item?id={story_id}"


def _search_story_ids(query: str, *, max_hits_per_query: int, timeout: int) -> list[int]:
    params = urlencode(
        {
            "query": query,
            "tags": "story",
            "hitsPerPage": max_hits_per_query,
        }
    )
    payload = _request_json(f"{HN_SEARCH_API_ROOT}/search_by_date?{params}", timeout=timeout)
    if not isinstance(payload, dict):
        raise HackerNewsError("invalid search payload for search_by_date")

    hits = payload.get("hits")
    if not isinstance(hits, list):
        raise HackerNewsError("invalid search hits payload for search_by_date")

    story_ids: list[int] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        story_id = _story_id_from_search_hit(hit)
        if story_id is None:
            continue
        story_ids.append(story_id)
    return story_ids


def _story_id_from_search_hit(hit: dict[str, Any]) -> int | None:
    tags = {str(tag).strip().lower() for tag in hit.get("_tags") or []}
    if "story" not in tags:
        return None
    return _coerce_positive_int(hit.get("story_id") or hit.get("objectID"))


def _fetch_story_by_id(
    raw_story_id: object,
    *,
    position: int,
    context_label: str,
    fetch_top_comments: bool,
    max_top_comments: int,
    timeout: int,
    query: str = "",
) -> HackerNewsStory | None:
    story_id = _coerce_positive_int(raw_story_id)
    if story_id is None:
        return None

    item = _request_json(f"{HN_API_ROOT}/item/{story_id}.json", timeout=timeout)
    if not isinstance(item, dict):
        return None
    if item.get("type") != "story" or item.get("deleted") or item.get("dead"):
        return None

    title = html.unescape(str(item.get("title") or "")).strip()
    story_text = clean_html_text(item.get("text") or "")
    top_comments = (
        _fetch_top_level_comments(item.get("kids") or [], max_top_comments=max_top_comments, timeout=timeout)
        if fetch_top_comments
        else []
    )
    return HackerNewsStory(
        story_id=story_id,
        title=title,
        discussion_url=discussion_url(story_id),
        external_url=str(item.get("url") or "").strip(),
        author=str(item.get("by") or "").strip(),
        created_at=_iso_from_epoch(item.get("time")),
        score=int(item.get("score") or 0),
        descendants=int(item.get("descendants") or 0),
        position=position,
        text_preview=story_text or title,
        story_list_name=context_label,
        top_comments=top_comments,
        query=query,
    )


def _fetch_top_level_comments(kids: list[object], *, max_top_comments: int, timeout: int) -> list[str]:
    comments: list[str] = []
    for raw_comment_id in kids:
        comment_id = int(raw_comment_id)
        item = _request_json(f"{HN_API_ROOT}/item/{comment_id}.json", timeout=timeout)
        if not isinstance(item, dict):
            continue
        if item.get("type") != "comment" or item.get("deleted") or item.get("dead"):
            continue
        text = clean_html_text(item.get("text") or "")
        if not text:
            continue
        comments.append(text)
        if len(comments) >= max_top_comments:
            break
    return comments


def _request_json(url: str, *, timeout: int) -> Any:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raise HackerNewsError(f"HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise HackerNewsError(f"request failed for {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise HackerNewsError(f"invalid JSON from {url}") from exc


def _iso_from_epoch(epoch: object) -> str:
    if not epoch:
        return ""
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


__all__ = [
    "HackerNewsError",
    "HackerNewsStory",
    "SUPPORTED_STORY_LISTS",
    "clean_html_text",
    "discussion_url",
    "fetch_hackernews_search_stories",
    "fetch_hackernews_stories",
    "validate_story_list",
]
