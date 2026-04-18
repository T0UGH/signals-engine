"""Hacker News Firebase API source for hacker-news-watch."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


USER_AGENT = "signals-engine/0.1 hacker-news-watch"
HN_API_ROOT = "https://hacker-news.firebaseio.com/v0"
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
        story_id = int(raw_story_id)
        item = _request_json(f"{HN_API_ROOT}/item/{story_id}.json", timeout=timeout)
        if not isinstance(item, dict):
            continue
        if item.get("deleted") or item.get("dead"):
            continue

        title = html.unescape(str(item.get("title") or "")).strip()
        story_text = clean_html_text(item.get("text") or "")
        top_comments = (
            _fetch_top_level_comments(item.get("kids") or [], max_top_comments=max_top_comments, timeout=timeout)
            if fetch_top_comments
            else []
        )
        stories.append(
            HackerNewsStory(
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
                story_list_name=endpoint_name,
                top_comments=top_comments,
            )
        )
    return stories


def discussion_url(story_id: int) -> str:
    return f"https://news.ycombinator.com/item?id={story_id}"


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


__all__ = [
    "HackerNewsError",
    "HackerNewsStory",
    "SUPPORTED_STORY_LISTS",
    "clean_html_text",
    "discussion_url",
    "fetch_hackernews_stories",
    "validate_story_list",
]
