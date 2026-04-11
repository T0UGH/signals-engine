"""Reddit public JSON source for query-based watch lanes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

USER_AGENT = "signals-engine/0.1 reddit-watch"
MAX_RETRIES = 3
BASE_BACKOFF = 2.0


@dataclass
class RedditThread:
    thread_id: str
    title: str
    subreddit: str
    author: str
    score: int
    num_comments: int
    created_at: str
    url: str
    permalink: str
    body: str
    top_comments: list[str]


def _request_json(url: str, timeout: int = 15) -> dict[str, Any] | list[Any]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    req = Request(url, headers=headers)
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            with urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "json" not in content_type and "text/html" in content_type:
                    raise RedditPublicError(f"anti-bot HTML response from {url}")
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < MAX_RETRIES - 1:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else BASE_BACKOFF * (2 ** attempt)
                time.sleep(delay)
                continue
            raise RedditPublicError(f"HTTP {exc.code} for {url}") from exc
        except URLError as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(BASE_BACKOFF * (2 ** attempt))
                continue
            raise RedditPublicError(f"request failed for {url}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RedditPublicError(f"invalid JSON from {url}") from exc
    raise RedditPublicError(f"request failed for {url}: {last_error}")


class RedditPublicError(RuntimeError):
    """Raised when Reddit public retrieval fails."""


def _iso_from_epoch(epoch: float | int | None) -> str:
    if not epoch:
        return ""
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cutoff_epoch(lookback_days: int) -> float:
    return (datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp()


def _extract_top_comments(permalink: str, limit: int = 3) -> list[str]:
    if not permalink:
        return []
    url = f"https://www.reddit.com{permalink}.json?limit=10&sort=top"
    data = _request_json(url)
    if not isinstance(data, list) or len(data) < 2:
        return []
    listing = data[1]
    children = (((listing or {}).get("data") or {}).get("children") or [])
    comments: list[str] = []
    for child in children:
        comment = child.get("data", {}) if isinstance(child, dict) else {}
        body = (comment.get("body") or "").strip()
        if not body or body in ("[deleted]", "[removed]"):
            continue
        comments.append(html.unescape(" ".join(body.split())))
        if len(comments) >= limit:
            break
    return comments


def fetch_reddit_threads(
    query: str,
    *,
    lookback_days: int = 30,
    max_threads: int = 10,
    subreddits: list[str] | None = None,
) -> list[RedditThread]:
    """Fetch recent Reddit threads via the public JSON search endpoints."""
    encoded = quote_plus(query)
    cutoff = _cutoff_epoch(lookback_days)
    urls: list[str] = []
    if subreddits:
        for sub in subreddits:
            cleaned = sub.strip().lstrip("r/")
            if cleaned:
                urls.append(
                    f"https://www.reddit.com/r/{cleaned}/search.json?q={encoded}&restrict_sr=on&sort=relevance&t=month&limit={max_threads}"
                )
    else:
        urls.append(f"https://www.reddit.com/search.json?q={encoded}&sort=relevance&t=month&limit={max_threads}")

    threads: list[RedditThread] = []
    seen_ids: set[str] = set()
    for url in urls:
        payload = _request_json(url)
        children = (((payload or {}).get("data") or {}).get("children") or []) if isinstance(payload, dict) else []
        for child in children:
            post = child.get("data", {}) if isinstance(child, dict) else {}
            thread_id = str(post.get("id") or "").strip()
            if not thread_id or thread_id in seen_ids:
                continue
            created_epoch = float(post.get("created_utc") or 0)
            if created_epoch and created_epoch < cutoff:
                continue
            seen_ids.add(thread_id)
            title = html.unescape((post.get("title") or "").strip())
            body = html.unescape((post.get("selftext") or "").strip())
            permalink = str(post.get("permalink") or "")
            url_value = str(post.get("url") or "")
            if permalink and url_value.startswith("/"):
                url_value = f"https://www.reddit.com{permalink}"
            threads.append(
                RedditThread(
                    thread_id=thread_id,
                    title=title,
                    subreddit=str(post.get("subreddit") or ""),
                    author=str(post.get("author") or ""),
                    score=int(post.get("score") or 0),
                    num_comments=int(post.get("num_comments") or 0),
                    created_at=_iso_from_epoch(created_epoch),
                    url=url_value or f"https://www.reddit.com{permalink}",
                    permalink=permalink,
                    body=body,
                    top_comments=_extract_top_comments(permalink, limit=3),
                )
            )
            if len(threads) >= max_threads:
                return threads
    return threads


__all__ = ["RedditThread", "RedditPublicError", "fetch_reddit_threads"]
