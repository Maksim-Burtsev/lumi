from datetime import UTC, datetime

from sqlalchemy import select

from lumi.connectors.news.rss import FetchedNewsItem
from lumi.db.models import NewsItem
from lumi.db.session import session_scope
from lumi.llm.gateway import LLMGateway
from lumi.llm.mock import MockLLMProvider
from lumi.services.news import NewsService
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


class FakeRss:
    def __init__(self, items: list[FetchedNewsItem]) -> None:
        self.items = items

    async def fetch_topic(self, **kwargs) -> list[FetchedNewsItem]:
        return self.items


def _item(url: str, title: str) -> FetchedNewsItem:
    from lumi.connectors.news.rss import url_hash

    return FetchedNewsItem(
        title=title, url=url, source_name="Test Source",
        published_at=datetime(2026, 6, 10, 8, tzinfo=UTC),
        snippet="кратко", hash=url_hash(url),
    )


async def test_collect_dedupes_by_hash(user):
    items = [_item("https://a.example/1", "Новость 1"), _item("https://a.example/2", "Новость 2")]
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = NewsService(session, llm=LLMGateway(MockLLMProvider()), connector=FakeRss(items))
        topic = await service.create_topic(u, title="AI", query="AI agents")
        first = await service.collect_news(u, topic)
        assert len(first) == 2
        # Second collection of the same items must not duplicate.
        second = await service.collect_news(u, topic)
        assert len(second) == 2

    async with session_scope() as session:
        rows = (await session.execute(select(NewsItem))).scalars().all()
        assert len(rows) == 2


async def test_generate_digest_saves_run(user):
    items = [_item("https://a.example/1", "Большой релиз LLM")]
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = NewsService(session, llm=LLMGateway(MockLLMProvider()), connector=FakeRss(items))
        await service.create_topic(u, title="AI", query="AI")
        digest = await service.generate_digest(u)
        assert digest is not None
        assert digest.digest_text
        assert len(digest.items_json) == 1

        digests = await service.list_digests(u)
        assert len(digests) == 1


async def test_no_topics_returns_none(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = NewsService(session, llm=LLMGateway(MockLLMProvider()), connector=FakeRss([]))
        assert await service.generate_digest(u) is None
