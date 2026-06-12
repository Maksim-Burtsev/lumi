"""RSS / Google News fetching for news topics."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

import feedparser
import httpx

from lumi.logging import get_logger

log = get_logger(__name__)

FETCH_TIMEOUT = 20.0


@dataclass(slots=True)
class FetchedNewsItem:
    title: str
    url: str
    source_name: str | None
    published_at: datetime | None
    snippet: str | None
    hash: str


def google_news_rss_url(query: str, language: str = "ru") -> str:
    """Google News search RSS for a query."""
    if language.startswith("ru"):
        params = "hl=ru&gl=RU&ceid=RU:ru"
    else:
        params = "hl=en-US&gl=US&ceid=US:en"
    return f"https://news.google.com/rss/search?q={quote(query)}&{params}"


def _entry_published(entry) -> datetime | None:  # type: ignore[no-untyped-def]
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                continue
    return None


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


class RssNewsConnector:
    async def fetch_topic(
        self,
        *,
        query: str,
        language: str = "ru",
        max_items: int = 10,
        feed_urls: list[str] | None = None,
    ) -> list[FetchedNewsItem]:
        """Fetch items for a topic: explicit RSS feeds or Google News search RSS."""
        urls = feed_urls or [google_news_rss_url(query, language)]
        items: list[FetchedNewsItem] = []
        seen: set[str] = set()
        for feed_url in urls:
            try:
                async with httpx.AsyncClient(
                    timeout=FETCH_TIMEOUT, follow_redirects=True,
                    headers={"User-Agent": "Lumi/0.1 (+local personal assistant)"},
                ) as client:
                    resp = await client.get(feed_url)
                    resp.raise_for_status()
                feed = feedparser.parse(resp.content)
            except Exception as exc:  # noqa: BLE001 — a dead feed must not kill the digest
                log.warning("rss fetch failed", fields={"feed_url": feed_url, "error": str(exc)})
                continue

            source_title = (feed.feed.get("title") if feed.feed else None) or None
            for entry in feed.entries:
                link = entry.get("link") or ""
                title = (entry.get("title") or "").strip()
                if not link or not title:
                    continue
                item_hash = url_hash(link)
                if item_hash in seen:
                    continue
                seen.add(item_hash)
                snippet = (entry.get("summary") or entry.get("description") or "").strip() or None
                if snippet and len(snippet) > 500:
                    snippet = snippet[:500]
                source = entry.get("source", {})
                source_name = (source.get("title") if isinstance(source, dict) else None) or source_title
                items.append(
                    FetchedNewsItem(
                        title=title[:500],
                        url=link,
                        source_name=source_name,
                        published_at=_entry_published(entry),
                        snippet=snippet,
                        hash=item_hash,
                    )
                )
                if len(items) >= max_items:
                    break
            if len(items) >= max_items:
                break
        return items
