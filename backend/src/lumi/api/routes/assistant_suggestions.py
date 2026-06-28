"""Assistant suggestions API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import assistant_suggestion_to_dict
from lumi.db.models import User
from lumi.services.assistant_suggestions import AssistantSuggestionService

router = APIRouter()


async def _get_suggestion_or_404(
    service: AssistantSuggestionService,
    user: User,
    suggestion_id: str,
):
    try:
        parsed = uuid.UUID(suggestion_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    suggestion = await service.get(user, parsed)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="not_found")
    return suggestion


@router.get("/assistant/suggestions")
async def list_suggestions(
    kind: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    suggestions = await AssistantSuggestionService(session).list_pending(user, kind=kind)
    return {"items": [assistant_suggestion_to_dict(suggestion) for suggestion in suggestions]}


@router.post("/assistant/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(
    suggestion_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = AssistantSuggestionService(session)
    suggestion = await _get_suggestion_or_404(service, user, suggestion_id)
    suggestion = await service.dismiss(user, suggestion)
    return {"suggestion": assistant_suggestion_to_dict(suggestion)}


@router.post("/assistant/suggestions/{suggestion_id}/accept")
async def accept_suggestion(
    suggestion_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = AssistantSuggestionService(session)
    suggestion = await _get_suggestion_or_404(service, user, suggestion_id)
    suggestion = await service.accept(user, suggestion)
    return {"suggestion": assistant_suggestion_to_dict(suggestion)}
