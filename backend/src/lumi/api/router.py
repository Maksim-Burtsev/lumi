"""Aggregated /api router."""

from __future__ import annotations

from fastapi import APIRouter

from lumi.api.routes import (
    agent_runs,
    automations,
    calendar,
    connectors,
    debug,
    inbox,
    me,
    memory,
    news,
    tasks,
    today,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(me.router, tags=["me"])
api_router.include_router(today.router, tags=["today"])
api_router.include_router(tasks.router, tags=["tasks"])
api_router.include_router(calendar.router, tags=["calendar"])
api_router.include_router(inbox.router, tags=["inbox"])
api_router.include_router(news.router, tags=["news"])
api_router.include_router(automations.router, tags=["automations"])
api_router.include_router(memory.router, tags=["memory"])
api_router.include_router(agent_runs.router, tags=["agent-runs"])
api_router.include_router(connectors.router, tags=["connectors"])
api_router.include_router(debug.router, tags=["debug"])
