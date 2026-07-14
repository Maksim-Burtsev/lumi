"""Aggregated /api router."""

from __future__ import annotations

from fastapi import APIRouter

from lumi.api.routes import (
    agent_runs,
    assistant_suggestions,
    auth,
    calendar,
    confirmations,
    connectors,
    debug,
    focus,
    me,
    memory,
    projects,
    realtime,
    tasks,
    telegram,
    today,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(me.router, tags=["me"])
api_router.include_router(today.router, tags=["today"])
api_router.include_router(tasks.router, tags=["tasks"])
api_router.include_router(projects.router, tags=["projects"])
api_router.include_router(assistant_suggestions.router, tags=["assistant-suggestions"])
api_router.include_router(calendar.router, tags=["calendar"])
api_router.include_router(focus.router, tags=["focus"])
api_router.include_router(confirmations.router, tags=["confirmations"])
api_router.include_router(memory.router, tags=["memory"])
api_router.include_router(agent_runs.router, tags=["agent-runs"])
api_router.include_router(connectors.router, tags=["connectors"])
api_router.include_router(realtime.router, tags=["realtime"])
api_router.include_router(debug.router, tags=["debug"])
api_router.include_router(telegram.router, tags=["telegram"])
