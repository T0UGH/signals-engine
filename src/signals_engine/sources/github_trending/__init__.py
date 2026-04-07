"""GitHub Trending Weekly data source.

Fetches and parses the GitHub Trending Weekly HTML page to extract repo list.
Does NOT require authentication — GitHub trending pages are public.
"""

from __future__ import annotations

import re
import httpx
from dataclasses import dataclass


@dataclass
class TrendingRepo:
    """A single repo from the GitHub Trending Weekly page."""
    rank: int
    repo: str  # "owner/repo"
    description: str
    language: str
    stars_this_week: int
    html_url: str


class TrendingError(Exception):
    """Failed to fetch or parse the trending page."""
    pass


def fetch_trending_weekly(
    url: str = "https://github.com/trending?since=weekly",
    max_repos: int = 30,
    timeout: int = 30,
) -> list[TrendingRepo]:
    """Fetch and parse GitHub Trending Weekly page.

    Args:
        url: GitHub trending URL. Default: weekly trending.
        max_repos: Maximum number of repos to return (default 30).
        timeout: HTTP request timeout in seconds (default 30).

    Returns:
        List of TrendingRepo objects, ordered by rank (1 = top).

    Raises:
        TrendingError: on network failure or unexpected page structure.
    """
    try:
        transport = httpx.HTTPTransport(retries=1)
        client = httpx.Client(transport=transport, timeout=timeout)
        try:
            response = client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html",
                },
            )
        finally:
            client.close()
    except httpx.TimeoutException as e:
        raise TrendingError(f"Request timed out after {timeout}s: {e}") from e
    except httpx.RequestError as e:
        raise TrendingError(f"Request failed: {e}") from e

    if response.status_code != 200:
        raise TrendingError(f"Unexpected status {response.status_code} fetching trending page")

    html = response.text
    return _parse_trending_html(html, max_repos)


def _parse_trending_html(html: str, max_repos: int) -> list[TrendingRepo]:
    """Parse GitHub Trending HTML into TrendingRepo list.

    Uses regex parsing (same approach as the original shell implementation)
    to avoid adding BeautifulSoup as a dependency.
    """
    repos: list[TrendingRepo] = []

    article_pattern = re.compile(
        r'<article class="Box-row">(.*?)</article>',
        re.DOTALL,
    )
    repo_pattern = re.compile(
        r'<h2[^>]*>.*?<a[^>]*href="(/[^"]+)"',
        re.DOTALL,
    )
    desc_pattern = re.compile(
        r'<p class="col-9[^"]*"[^>]*>(.*?)</p>',
        re.DOTALL,
    )
    lang_pattern = re.compile(
        r'<span itemprop="programmingLanguage">(.*?)</span>',
        re.DOTALL,
    )
    stars_pattern = re.compile(
        r'([\d,]+)\s*stars?\s*this\s*week',
        re.IGNORECASE,
    )

    articles = article_pattern.findall(html)
    for i, article in enumerate(articles[:max_repos], start=1):
        repo_match = repo_pattern.search(article)
        if not repo_match:
            continue
        repo_path = repo_match.group(1).strip("/")
        if "/" not in repo_path:
            continue

        # Description: strip HTML tags
        desc_match = desc_pattern.search(article)
        if desc_match:
            raw_desc = desc_match.group(1)
            desc = re.sub(r'<[^>]+>', '', raw_desc).strip()
        else:
            desc = ""

        # Language
        lang_match = lang_pattern.search(article)
        lang = lang_match.group(1).strip() if lang_match else ""

        # Stars this week
        stars_match = stars_pattern.search(article)
        if stars_match:
            stars_str = stars_match.group(1).replace(",", "")
            stars_this_week = int(stars_str)
        else:
            stars_this_week = 0

        repos.append(TrendingRepo(
            rank=i,
            repo=repo_path,
            description=desc,
            language=lang,
            stars_this_week=stars_this_week,
            html_url=f"https://github.com/{repo_path}",
        ))

    return repos
