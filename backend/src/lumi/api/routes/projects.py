"""Projects API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import project_to_dict
from lumi.db.models import User
from lumi.services.projects import ProjectService

router = APIRouter()


@router.get("/projects")
async def list_projects(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    summaries = await ProjectService(session).list_summaries(user)
    return {
        "items": [
            project_to_dict(
                summary.project,
                active_task_count=summary.active_task_count,
                completed_task_count=summary.completed_task_count,
                estimated_minutes_total=summary.estimated_minutes_total,
                health_status=summary.health_status,
                health_reason=summary.health_reason,
                next_task=summary.next_task,
                timezone=user.timezone,
            )
            for summary in summaries
        ]
    }
