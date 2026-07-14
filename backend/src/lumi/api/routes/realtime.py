"""Realtime SSE endpoint for Mini App query invalidation."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from lumi.api.deps import INIT_DATA_HEADER, resolve_current_user
from lumi.db.models import UiEvent, User
from lumi.db.session import get_session_factory, session_scope
from lumi.security.web_auth import WEB_SESSION_COOKIE
from lumi.services.realtime import (
    RealtimeEventService,
    commit_with_realtime,
    realtime_hub,
    rollback_with_realtime,
)

router = APIRouter()

HEARTBEAT_SECONDS = 25
SSE_OPEN_PADDING_BYTES = 2048


async def authenticate_realtime_user(request: Request) -> User:
    factory = get_session_factory()
    async with factory() as session:
        try:
            user = await resolve_current_user(request, session)
            await commit_with_realtime(session)
            return user
        except HTTPException:
            await rollback_with_realtime(session)
            raise
        except BaseException:
            await rollback_with_realtime(session)
            raise


async def revalidate_realtime_web_session(request: Request, user: User) -> bool:
    """Close an existing SSE stream after its standalone session is revoked."""
    if request.headers.get(INIT_DATA_HEADER) or not request.cookies.get(WEB_SESSION_COOKIE):
        return True
    try:
        current = await authenticate_realtime_user(request)
    except HTTPException:
        return False
    return current.id == user.id


def _sse(event_name: str, data: dict, *, event_id: int | None = None) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event_name}\ndata: {payload}\n\n"


def _event_data(event: UiEvent) -> dict:
    return {
        "id": event.id,
        "topics": event.topics,
        "event_type": event.event_type,
        "payload": event.payload,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


@router.get("/realtime")
async def realtime_stream(
    request: Request,
    after: int = Query(default=0, ge=0),
) -> StreamingResponse:
    user = await authenticate_realtime_user(request)

    async def stream():
        last_sent = after
        if not await revalidate_realtime_web_session(request, user):
            return
        yield f": {' ' * SSE_OPEN_PADDING_BYTES}\n\n"
        yield ": connected\n\n"

        async with session_scope() as session:
            catchup = await RealtimeEventService(session).list_after(user.id, after=after)
        for event in catchup:
            if not await revalidate_realtime_web_session(request, user):
                return
            last_sent = max(last_sent, event.id)
            yield _sse("ui_event", _event_data(event), event_id=event.id)

        async with realtime_hub.subscribe(user.id) as queue:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    if not await revalidate_realtime_web_session(request, user):
                        break
                    yield ": heartbeat\n\n"
                    continue

                if not await revalidate_realtime_web_session(request, user):
                    break
                if message.get("event_type") == "resync":
                    yield _sse("resync", {
                        "topics": ["*"],
                        "event_type": "resync",
                        "payload": message.get("payload") or {},
                    })
                    continue

                event_id = int(message.get("id") or 0)
                if event_id <= last_sent:
                    continue
                last_sent = event_id
                yield _sse(
                    "ui_event",
                    {
                        "id": event_id,
                        "topics": message.get("topics") or [],
                        "event_type": message.get("event_type") or "ui.changed",
                        "payload": message.get("payload") or {},
                        "created_at": message.get("created_at"),
                    },
                    event_id=event_id,
                )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
