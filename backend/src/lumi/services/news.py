"""NewsService: topics, collection with dedupe, LLM digest generation."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.prompts import NEWS_DIGEST_SYSTEM
from lumi.config import get_settings
from lumi.connectors.news.rss import FetchedNewsItem, RssNewsConnector
from lumi.db.models import NewsDigestRun, NewsItem, NewsTopic, User
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import get_logger
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import fmt_local, local_now

log = get_logger(__name__)


class NewsService:
    def __init__(self, session: AsyncSession, *, llm: LLMGateway | None = None,
                 connector: RssNewsConnector | None = None) -> None:
        self.session = session
        self.llm = llm or LLMGateway()
        self.connector = connector or RssNewsConnector()

    # --- topics ---------------------------------------------------------

    async def list_topics(self, user: User) -> list[NewsTopic]:
        result = await self.session.execute(
            select(NewsTopic).where(NewsTopic.user_id == user.id).order_by(NewsTopic.created_at)
        )
        return list(result.scalars())

    async def get_topic(self, user: User, topic_id: uuid.UUID) -> NewsTopic | None:
        result = await self.session.execute(
            select(NewsTopic).where(NewsTopic.id == topic_id, NewsTopic.user_id == user.id)
        )
        return result.scalar_one_or_none()

    async def create_topic(
        self, user: User, *, title: str, query: str, language: str = "ru",
        config: dict[str, Any] | None = None,
    ) -> NewsTopic:
        topic = NewsTopic(
            user_id=user.id, title=title.strip()[:200], query=query.strip()[:500],
            language=language, config=config or {},
        )
        self.session.add(topic)
        await self.session.flush()
        await RealtimeEventService(self.session).emit(
            user_id=user.id,
            topics=["news"],
            event_type="news_topic.created",
            payload={"topic_id": str(topic.id)},
        )
        return topic

    # --- collection -------------------------------------------------------

    async def collect_news(self, user: User, topic: NewsTopic) -> list[NewsItem]:
        """Fetch RSS for the topic, dedupe by URL hash, persist new items."""
        settings = get_settings()
        max_items = topic.config.get("max_items", settings.news_max_items_per_topic)
        feed_urls = topic.config.get("feed_urls") or None
        fetched = await self.connector.fetch_topic(
            query=topic.query, language=topic.language, max_items=max_items, feed_urls=feed_urls
        )
        if not fetched:
            return []
        return await self._upsert_items(user, topic, fetched)

    async def _upsert_items(
        self, user: User, topic: NewsTopic, fetched: list[FetchedNewsItem]
    ) -> list[NewsItem]:
        hashes = [f.hash for f in fetched]
        rows = [
            {
                "user_id": user.id,
                "topic_id": topic.id,
                "title": f.title,
                "url": f.url,
                "source_name": f.source_name,
                "published_at": f.published_at,
                "snippet": f.snippet,
                "hash": f.hash,
            }
            for f in fetched
        ]
        stmt = pg_insert(NewsItem).values(rows).on_conflict_do_nothing(
            index_elements=["user_id", "hash"]
        )
        await self.session.execute(stmt)
        result = await self.session.execute(
            select(NewsItem).where(NewsItem.user_id == user.id, NewsItem.hash.in_(hashes))
        )
        return list(result.scalars())

    # --- digest ------------------------------------------------------------

    async def generate_digest(
        self, user: User, *, agent_run_id: uuid.UUID | None = None
    ) -> NewsDigestRun | None:
        """Collect all enabled topics and produce one LLM digest. None if no topics."""
        topics = [t for t in await self.list_topics(user) if t.enabled]
        if not topics:
            return None

        sections: list[str] = []
        all_items: list[dict[str, Any]] = []
        for topic in topics:
            items = await self.collect_news(user, topic)
            if not items:
                sections.append(f"Topic: {topic.title}\n(no new items found)")
                continue
            lines = []
            for item in items:
                line = f"- {item.title}"
                if item.source_name:
                    line += f" — {item.source_name}"
                if item.snippet:
                    line += f"\n  {item.snippet[:300]}"
                lines.append(line)
                all_items.append({
                    "id": str(item.id), "title": item.title, "url": item.url,
                    "source": item.source_name, "topic": topic.title,
                })
            sections.append(f"Topic: {topic.title}\n" + "\n".join(lines))

        now_local = local_now(user.timezone)
        user_content = (
            f"Target language: {user.locale or 'en'}\n"
            f"Date: {now_local.strftime('%Y-%m-%d %H:%M')}\n"
            f"User topics: {', '.join(t.title for t in topics)}\n\n"
            + "\n\n".join(sections)
        )
        try:
            response = await self.llm.complete(
                messages=[LLMMessage(role="user", content=user_content)],
                system=NEWS_DIGEST_SYSTEM,
                temperature=0.3,
                max_tokens=2048,
                request_kind="news_digest",
                user_id=user.id,
                agent_run_id=agent_run_id,
                session=self.session,
            )
            digest_text = response.text.strip()
        except Exception as exc:  # noqa: BLE001 — degrade to a plain headline list
            log.warning("news digest LLM failed, falling back to headlines",
                        fields={"error": str(exc)})
            if not all_items:
                raise
            digest_text = "Fresh items for your topics:\n\n" + "\n".join(
                f"• {i['title']}" + (f" ({i['source']})" if i["source"] else "")
                for i in all_items[:15]
            )

        digest = NewsDigestRun(
            user_id=user.id,
            agent_run_id=agent_run_id,
            title=f"Digest {fmt_local(now_local, user.timezone, '%d.%m %H:%M')}",
            digest_text=digest_text,
            items_json=all_items,
        )
        self.session.add(digest)
        await self.session.flush()
        await RealtimeEventService(self.session).emit(
            user_id=user.id,
            topics=["news"],
            event_type="news_digest.created",
            payload={"digest_id": str(digest.id)},
        )
        return digest

    async def list_digests(self, user: User, limit: int = 5) -> list[NewsDigestRun]:
        result = await self.session.execute(
            select(NewsDigestRun)
            .where(NewsDigestRun.user_id == user.id)
            .order_by(NewsDigestRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())
