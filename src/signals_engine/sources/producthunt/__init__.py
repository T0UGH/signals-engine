"""Product Hunt data source via GraphQL API v2.

Fetches featured products and matches them against configured topics.
"""
from __future__ import annotations

import os
import re
import httpx
from dataclasses import dataclass, field


PH_GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"

# GraphQL query — fetches recent posts sorted by votes
PH_QUERY = """query($postedAfter: DateTime!, $first: Int!, $after: String) {
  posts(postedAfter: $postedAfter, first: $first, after: $after, order: VOTES) {
    edges {
      node {
        id
        slug
        name
        tagline
        description
        votesCount
        commentsCount
        createdAt
        featuredAt
        website
        url
        topics { edges { node { slug name } } }
        makers { name username }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""


@dataclass
class Maker:
    name: str
    username: str


@dataclass
class Topic:
    slug: str
    name: str


@dataclass
class Post:
    id: str
    slug: str
    name: str
    tagline: str
    description: str
    votes_count: int
    comments_count: int
    created_at: str
    featured_at: str
    website: str
    url: str
    topics: list[Topic]
    makers: list[Maker]

    @property
    def is_featured(self) -> bool:
        return bool(self.featured_at)


class PHError(Exception):
    """Product Hunt API error."""
    pass


def _to_slug(name: str) -> str:
    """Convert a human-readable topic name to a URL slug."""
    return name.lower().replace(" ", "-")


def _fetch_page(
    token: str,
    posted_after: str,
    first: int = 20,
    after: str | None = None,
    timeout: int = 30,
) -> dict:
    """Fetch one page of Product Hunt posts via GraphQL API."""
    variables: dict = {"postedAfter": posted_after, "first": first}
    if after:
        variables["after"] = after

    payload = {"query": PH_QUERY, "variables": variables}

    try:
        transport = httpx.HTTPTransport(retries=1)
        client = httpx.Client(transport=transport, timeout=timeout)
        try:
            response = client.post(
                PH_GRAPHQL_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            )
        finally:
            client.close()
    except httpx.TimeoutException as e:
        raise PHError(f"Request timed out after {timeout}s: {e}") from e
    except httpx.RequestError as e:
        raise PHError(f"Request failed: {e}") from e

    if response.status_code == 401:
        raise PHError("HTTP 401 — PH_API_TOKEN may be invalid or expired")
    if response.status_code >= 500:
        raise PHError(f"Product Hunt server error: HTTP {response.status_code}")

    data = response.json()

    errors = data.get("errors")
    if errors:
        raise PHError(f"GraphQL error: {errors[0].get('message', errors[0])}")

    return data


def _parse_post(node: dict) -> Post:
    """Parse a single post node from the GraphQL response."""
    topics = [
        Topic(slug=t["node"]["slug"], name=t["node"]["name"])
        for t in node.get("topics", {}).get("edges", [])
        if t.get("node")
    ]
    makers = [
        Maker(name=m.get("name", ""), username=m.get("username", ""))
        for m in node.get("makers", []) or []
        if m
    ]
    return Post(
        id=str(node.get("id", "")),
        slug=str(node.get("slug", "")),
        name=str(node.get("name", "")),
        tagline=str(node.get("tagline") or ""),
        description=str(node.get("description") or ""),
        votes_count=int(node.get("votesCount") or 0),
        comments_count=int(node.get("commentsCount") or 0),
        created_at=str(node.get("createdAt") or ""),
        featured_at=str(node.get("featuredAt") or ""),
        website=str(node.get("website") or ""),
        url=str(node.get("url") or ""),
        topics=topics,
        makers=makers,
    )


def fetch_posts(
    token: str,
    posted_after: str,
    max_pages: int = 3,
    timeout: int = 30,
) -> list[Post]:
    """Fetch recent Product Hunt posts with cursor pagination.

    Args:
        token: Product Hunt API bearer token.
        posted_after: ISO datetime string (e.g. "2026-04-07T00:00:00Z").
        max_pages: Maximum number of pages to fetch (default 3).
        timeout: HTTP request timeout in seconds (default 30).

    Returns:
        List of all Post objects fetched across all pages.

    Raises:
        PHError: on authentication failure or API error.
    """
    all_posts: list[Post] = []
    cursor: str | None = None

    for page in range(max_pages):
        data = _fetch_page(token, posted_after, first=20, after=cursor, timeout=timeout)

        posts_data = data.get("data", {}).get("posts", {})
        edges = posts_data.get("edges", [])
        page_info = posts_data.get("pageInfo", {})

        for edge in edges:
            node = edge.get("node")
            if node:
                all_posts.append(_parse_post(node))

        has_next = page_info.get("hasNextPage", False)
        if not has_next:
            break

        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return all_posts


def match_posts_by_topics(
    posts: list[Post],
    topic_names: list[str],
) -> list[tuple[Post, Topic]]:
    """Match posts against configured topic names.

    Returns:
        List of (Post, Topic) tuples for featured products that match
        at least one configured topic.
    """
    # Build set of topic slugs to match
    topic_slugs = {_to_slug(name) for name in topic_names}
    hits: list[tuple[Post, Topic]] = []

    for post in posts:
        if not post.is_featured:
            continue
        for topic in post.topics:
            if topic.slug in topic_slugs:
                hits.append((post, topic))
                break  # One signal per post per run, not per topic

    return hits
