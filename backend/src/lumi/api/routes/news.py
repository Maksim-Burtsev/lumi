"""News API: topics, digests, run."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.run_helper import start_background_run
from lumi.api.serializers import digest_to_dict, topic_to_dict
from lumi.db.models import User
from lumi.services.news import NewsService

router = APIRouter()


class TopicCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=500)
    language: str = "ru"


class TopicPatch(BaseModel):
    title: str | None = None
    query: str | None = None
    language: str | None = None
    enabled: bool | None = None


@router.get("/news/topics")
async def list_topics(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    topics = await NewsService(session).list_topics(user)
    return {"items": [topic_to_dict(t) for t in topics]}


@router.post("/news/topics", status_code=201)
async def create_topic(
    payload: TopicCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    topic = await NewsService(session).create_topic(
        user, title=payload.title, query=payload.query, language=payload.language
    )
    return {"topic": topic_to_dict(topic)}


@router.patch("/news/topics/{topic_id}")
async def patch_topic(
    topic_id: str,
    payload: TopicPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = NewsService(session)
    try:
        topic = await service.get_topic(user, uuid.UUID(topic_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    if topic is None:
        raise HTTPException(status_code=404, detail="not_found")
    for key in ("title", "query", "language", "enabled"):
        value = getattr(payload, key)
        if value is not None:
            setattr(topic, key, value)
    return {"topic": topic_to_dict(topic)}


@router.get("/news/digests")
async def list_digests(
    limit: int = Query(default=5, le=20),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    digests = await NewsService(session).list_digests(user, limit=limit)
    return {"items": [digest_to_dict(d) for d in digests]}


@router.post("/news/digest/run")
async def run_digest(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await start_background_run(session, user, "news_digest")
