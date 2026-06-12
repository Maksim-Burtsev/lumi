from lumi.assistant.memory_service import MemoryService
from lumi.assistant.schemas import MemoryCandidate
from lumi.db.models import MemoryStatus
from lumi.db.session import session_scope
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


def _candidate(text: str, kind: str = "preference", importance: int = 3) -> MemoryCandidate:
    return MemoryCandidate(kind=kind, text=text, importance=importance, confidence=0.9)


async def test_store_and_dedup(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = MemoryService(session)
        first, created = await service.store_candidate(
            u, _candidate("Рабочие задачи лучше группировать по проектам")
        )
        assert created is True

        # Near-duplicate must update, not insert.
        second, created_again = await service.store_candidate(
            u, _candidate("рабочие задачи группировать по проектам", importance=5)
        )
        assert created_again is False
        assert second.id == first.id
        assert second.importance == 5

        memories = await service.list_memories(u)
        assert len(memories) == 1


async def test_retrieve_by_keyword(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = MemoryService(session)
        await service.store_candidate(u, _candidate("Дайджесты новостей присылать до 09:30 утра"))
        await service.store_candidate(u, _candidate("Кофе пользователь не пьет", kind="fact"))

        relevant = await service.retrieve_relevant(u, "когда присылать дайджест новостей?")
        assert relevant
        assert "дайджест" in relevant[0].text_.lower()
        assert relevant[0].last_accessed_at is not None


async def test_archive_and_delete(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        service = MemoryService(session)
        memory, _ = await service.store_candidate(u, _candidate("Временная заметка"))
        await service.archive_memory(u, memory)
        assert memory.status == MemoryStatus.ARCHIVED
        assert await service.list_memories(u, status="active") == []

        await service.delete_memory(u, memory)
        assert await service.list_memories(u, status="archived") == []
