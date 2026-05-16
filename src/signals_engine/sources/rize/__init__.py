"""Fetch and parse Rize AI tools weekly rankings."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.request

RIZE_AI_TOOLS_URL = "https://rize.io/ai-tools"

class RizeError(RuntimeError):
    """Raised when Rize rankings cannot be fetched or parsed."""

@dataclass(frozen=True)
class RizeTool:
    position: int
    name: str
    repo_url: str
    description: str

    @property
    def repo_slug(self) -> str:
        match = re.search(r"github\.com/([^/]+/[^/?#]+)", self.repo_url)
        return match.group(1) if match else self.name

def fetch_ai_tools(url: str = RIZE_AI_TOOLS_URL, timeout: int = 20) -> list[RizeTool]:
    """Fetch Rize's public weekly AI tools page and parse ranking items."""
    req = urllib.request.Request(url, headers={"User-Agent": "signals-engine/0.1 (+https://github.com/T0UGH/signals-engine)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except Exception as exc:  # pragma: no cover - network-specific
        raise RizeError(f"failed to fetch Rize AI tools page: {exc}") from exc
    return parse_ai_tools(html)

def parse_ai_tools(html: str) -> list[RizeTool]:
    """Parse Rize AI tools ItemList JSON-LD from an HTML document."""
    decoder = json.JSONDecoder()
    tools: list[RizeTool] = []
    for match in re.finditer(r'\{"@context":"https://schema\.org","@type":"ItemList"', html):
        try:
            obj, _ = decoder.raw_decode(html[match.start():])
        except json.JSONDecodeError:
            continue
        if obj.get("name") != "Trending AI tools this week":
            continue
        for item in obj.get("itemListElement", []):
            url = str(item.get("url") or "")
            name = str(item.get("name") or "").strip()
            if "github.com/" not in url or not name:
                continue
            try:
                position = int(item.get("position") or 0)
            except (TypeError, ValueError):
                position = 0
            tools.append(RizeTool(position=position, name=name, repo_url=url, description=str(item.get("description") or "").strip()))
        break
    if not tools:
        raise RizeError("could not find Rize 'Trending AI tools this week' ItemList")
    return sorted(tools, key=lambda item: item.position or 9999)
