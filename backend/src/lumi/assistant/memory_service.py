"""Long-term memory: store with dedup, retrieve by keyword/importance/recency."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.schemas import MemoryCandidate
from lumi.db.models import Memory, MemoryKind, MemoryStatus, User
from lumi.services.audit import AuditService
from lumi.services.realtime import RealtimeEventService
from lumi.utils.text import keyword_overlap, normalize_for_match
from lumi.utils.time import utc_now

DUPLICATE_OVERLAP_THRESHOLD = 0.75

_KIND_BOOST = {
    MemoryKind.INSTRUCTION: 3.0,
    MemoryKind.PREFERENCE: 2.0,
    MemoryKind.PROJECT: 1.5,
    MemoryKind.WORKFLOW: 1.0,
    MemoryKind.CONTACT: 0.5,
    MemoryKind.FACT: 0.5,
    MemoryKind.OTHER: 0.0,
}


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    async def list_memories(
        self, user: User, *, kind: str | None = None, status: str = "active", limit: int = 200
    ) -> list[Memory]:
        stmt = select(Memory).where(Memory.user_id == user.id)
        if status:
            stmt = stmt.where(Memory.status == MemoryStatus(status))
        if kind:
            stmt = stmt.where(Memory.kind == MemoryKind(kind))
        stmt = stmt.order_by(Memory.importance.desc(), Memory.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get(self, user: User, memory_id: uuid.UUID) -> Memory | None:
        result = await self.session.execute(
            select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------

    async def store_candidate(
        self,
        user: User,
        candidate: MemoryCandidate,
        *,
        source_message_id: uuid.UUID | None = None,
        source_agent_run_id: uuid.UUID | None = None,
        actor: str = "agent",
    ) -> tuple[Memory, bool]:
        """Store a memory candidate with dedup. Returns (memory, created)."""
        normalized = normalize_for_match(candidate.text)
        existing = await self.list_memories(user, status="active", limit=500)

        best_match: Memory | None = None
        best_overlap = 0.0
        for memory in existing:
            overlap = keyword_overlap(candidate.text, memory.text_)
            if overlap > best_overlap:
                best_overlap, best_match = overlap, memory

        if best_match is not None and best_overlap >= DUPLICATE_OVERLAP_THRESHOLD:
            # Duplicate: refresh importance/confidence instead of inserting.
            best_match.importance = max(best_match.importance, candidate.importance)
            best_match.confidence = max(float(best_match.confidence), candidate.confidence)
            if source_message_id and best_match.source_message_id is None:
                best_match.source_message_id = source_message_id
            await self.audit.log(user_id=user.id, actor=actor, entity_type="memory",
                                 entity_id=best_match.id, action="refreshed",
                                 details={"overlap": round(best_overlap, 2)})
            await self._emit_memory_changed(best_match, "memory.refreshed")
            return best_match, False

        memory = Memory(
            user_id=user.id,
            kind=MemoryKind(candidate.kind),
            status=MemoryStatus.ACTIVE,
            text_=candidate.text,
            normalized_text=normalized,
            importance=candidate.importance,
            confidence=candidate.confidence,
            source_message_id=source_message_id,
            source_agent_run_id=source_agent_run_id,
        )
        # Possible contradiction: moderate overlap with an existing memory.
        if best_match is not None and best_overlap >= 0.45:
            memory.metadata_ = {"potential_conflict": True, "conflicts_with": str(best_match.id)}
        self.session.add(memory)
        await self.session.flush()
        await self.audit.log(user_id=user.id, actor=actor, entity_type="memory",
                             entity_id=memory.id, action="stored",
                             details={"kind": candidate.kind})
        await self._emit_memory_changed(memory, "memory.stored")
        return memory, True

    # ------------------------------------------------------------------

    async def retrieve_relevant(self, user: User, query: str, limit: int = 12) -> list[Memory]:
        """Keyword/importance/recency scoring — no vector DB in MVP."""
        memories = await self.list_memories(user, status="active", limit=500)
        if not memories:
            return []
        now = utc_now()

        def score(memory: Memory) -> float:
            s = memory.importance * 3.0
            s += keyword_overlap(query, memory.text_) * 5.0
            if memory.tags:
                s += keyword_overlap(query, " ".join(memory.tags)) * 4.0
            if memory.last_accessed_at and now - memory.last_accessed_at < timedelta(days=7):
                s += 1.5
            s += _KIND_BOOST.get(memory.kind, 0.0)
            return s

        ranked = sorted(memories, key=score, reverse=True)[:limit]
        for memory in ranked:
            memory.last_accessed_at = now
        return ranked

    # ------------------------------------------------------------------

    async def archive_memory(self, user: User, memory: Memory, *, actor: str = "user") -> Memory:
        memory.status = MemoryStatus.ARCHIVED
        await self.audit.log(user_id=user.id, actor=actor, entity_type="memory",
                             entity_id=memory.id, action="archived", details={})
        await self._emit_memory_changed(memory, "memory.archived")
        return memory

    async def delete_memory(self, user: User, memory: Memory, *, actor: str = "user") -> None:
        await self.audit.log(user_id=user.id, actor=actor, entity_type="memory",
                             entity_id=memory.id, action="deleted", details={})
        await self._emit_memory_changed(memory, "memory.deleted")
        await self.session.delete(memory)

    async def _emit_memory_changed(self, memory: Memory, event_type: str) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=memory.user_id,
            topics=["memories"],
            event_type=event_type,
            payload={"memory_id": str(memory.id)},
        )
