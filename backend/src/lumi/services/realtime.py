"""Realtime UI invalidation events: Postgres outbox + Redis fanout."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.config import get_settings
from lumi.db.models import UiEvent
from lumi.logging import get_logger
from lumi.utils.time import utc_now

log = get_logger(__name__)

REALTIME_CHANNEL = "lumi:ui_events"
PENDING_REALTIME_EVENTS = "pending_realtime_events"
CLIENT_QUEUE_SIZE = 100
CATCH_UP_LIMIT = 500

RealtimeMessage = dict[str, Any]


def _event_to_message(event: UiEvent) -> RealtimeMessage:
    return {
        "id": event.id,
        "user_id": str(event.user_id),
        "topics": event.topics,
        "event_type": event.event_type,
        "payload": event.payload,
        "created_at": event.created_at.isoformat() if event.created_at else utc_now().isoformat(),
    }


async def publish_realtime_events(events: list[RealtimeMessage]) -> None:
    if not events:
        return
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        for event in events:
            await client.publish(
                REALTIME_CHANNEL,
                json.dumps(event, ensure_ascii=False, separators=(",", ":")),
            )
    finally:
        await client.aclose()


async def publish_pending_realtime_events(session: AsyncSession) -> None:
    events = list(session.info.pop(PENDING_REALTIME_EVENTS, []))
    if not events:
        return
    try:
        await publish_realtime_events(events)
    except Exception:  # noqa: BLE001 — outbox remains durable; clients catch up on reconnect
        log.exception("failed to publish realtime events", fields={"count": len(events)})


def clear_pending_realtime_events(session: AsyncSession) -> None:
    session.info.pop(PENDING_REALTIME_EVENTS, None)


async def commit_with_realtime(session: AsyncSession) -> None:
    await session.commit()
    await publish_pending_realtime_events(session)


async def rollback_with_realtime(session: AsyncSession) -> None:
    await session.rollback()
    clear_pending_realtime_events(session)


class RealtimeEventService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def emit(
        self,
        *,
        user_id: uuid.UUID,
        topics: list[str],
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> UiEvent:
        clean_topics = sorted({topic for topic in topics if topic})
        event = UiEvent(
            user_id=user_id,
            topics=clean_topics,
            event_type=event_type,
            payload=payload or {},
        )
        self.session.add(event)
        await self.session.flush()
        self.session.info.setdefault(PENDING_REALTIME_EVENTS, []).append(_event_to_message(event))
        return event

    async def list_after(
        self,
        user_id: uuid.UUID,
        *,
        after: int = 0,
        limit: int = CATCH_UP_LIMIT,
    ) -> list[UiEvent]:
        result = await self.session.execute(
            select(UiEvent)
            .where(UiEvent.user_id == user_id, UiEvent.id > after)
            .order_by(UiEvent.id)
            .limit(limit)
        )
        return list(result.scalars())

    async def delete_older_than(self, cutoff) -> int:
        result = await self.session.execute(delete(UiEvent).where(UiEvent.created_at < cutoff))
        return int(result.rowcount or 0)


class RealtimeHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[RealtimeMessage]]] = {}
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._stopped = False

    async def _ensure_started(self) -> None:
        async with self._lock:
            if self._task is None or self._task.done():
                self._stopped = False
                self._task = asyncio.create_task(self._run(), name="lumi-realtime-hub")

    @contextlib.asynccontextmanager
    async def subscribe(self, user_id: uuid.UUID) -> AsyncIterator[asyncio.Queue[RealtimeMessage]]:
        await self._ensure_started()
        key = str(user_id)
        queue: asyncio.Queue[RealtimeMessage] = asyncio.Queue(maxsize=CLIENT_QUEUE_SIZE)
        self._subscribers.setdefault(key, set()).add(queue)
        try:
            yield queue
        finally:
            queues = self._subscribers.get(key)
            if queues is not None:
                queues.discard(queue)
                if not queues:
                    self._subscribers.pop(key, None)

    async def close(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stopped:
            redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
            pubsub = redis.pubsub()
            try:
                await pubsub.subscribe(REALTIME_CHANNEL)
                async for raw in pubsub.listen():
                    if raw.get("type") != "message":
                        continue
                    try:
                        message = json.loads(raw["data"])
                    except (TypeError, json.JSONDecodeError):
                        log.warning("invalid realtime redis message")
                        continue
                    self._fanout(message)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — reconnect loop
                log.exception("realtime redis subscriber failed")
                await asyncio.sleep(1)
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe(REALTIME_CHANNEL)
                    await pubsub.aclose()
                await redis.aclose()

    def _fanout(self, message: RealtimeMessage) -> None:
        user_id = str(message.get("user_id") or "")
        for queue in list(self._subscribers.get(user_id, ())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                self._reset_queue(queue)

    @staticmethod
    def _reset_queue(queue: asyncio.Queue[RealtimeMessage]) -> None:
        with contextlib.suppress(asyncio.QueueEmpty):
            while True:
                queue.get_nowait()
        queue.put_nowait({
            "topics": ["*"],
            "event_type": "resync",
            "payload": {"reason": "client_queue_overflow"},
        })


realtime_hub = RealtimeHub()


async def close_realtime() -> None:
    await realtime_hub.close()
