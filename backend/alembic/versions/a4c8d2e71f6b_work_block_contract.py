"""enforce the work block ownership chain

Revision ID: a4c8d2e71f6b
Revises: 3d7a9c2f1b80
Create Date: 2026-07-16 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c8d2e71f6b"
down_revision: str | None = "3d7a9c2f1b80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Preserve legacy rows, but remove links that cannot satisfy the ownership contract.
    op.execute(
        """
        UPDATE calendar_events AS event
        SET source_task_id = NULL
        WHERE event.source_task_id IS NOT NULL
          AND (
            event.source <> 'internal'
            OR NOT EXISTS (
                SELECT 1
                FROM tasks AS task
                WHERE task.id = event.source_task_id
                  AND task.user_id = event.user_id
            )
          )
        """
    )
    op.execute(
        """
        UPDATE focus_sessions AS session
        SET task_id = NULL
        WHERE session.task_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM tasks AS task
              WHERE task.id = session.task_id
                AND task.user_id = session.user_id
          )
        """
    )

    op.create_unique_constraint("uq_tasks_user_id_id", "tasks", ["user_id", "id"])

    op.drop_constraint(
        "calendar_events_source_task_id_fkey",
        "calendar_events",
        type_="foreignkey",
    )
    op.create_unique_constraint(
        "uq_calendar_events_user_id_source_task",
        "calendar_events",
        ["user_id", "id", "source_task_id"],
    )
    op.create_index(
        "ix_calendar_events_user_source_task",
        "calendar_events",
        ["user_id", "source_task_id"],
    )
    op.create_check_constraint(
        "calendar_event_source_task_internal",
        "calendar_events",
        "source_task_id IS NULL OR source = 'internal'",
    )
    op.create_foreign_key(
        "fk_calendar_events_user_source_task",
        "calendar_events",
        "tasks",
        ["user_id", "source_task_id"],
        ["user_id", "id"],
        ondelete="RESTRICT",
    )

    op.add_column("focus_sessions", sa.Column("planned_event_id", sa.Uuid(), nullable=True))
    op.drop_constraint(
        "focus_sessions_task_id_fkey",
        "focus_sessions",
        type_="foreignkey",
    )
    op.create_index(
        "ix_focus_sessions_user_task",
        "focus_sessions",
        ["user_id", "task_id"],
    )
    op.create_index(
        "ix_focus_sessions_user_planned_event",
        "focus_sessions",
        ["user_id", "planned_event_id"],
    )
    op.create_check_constraint(
        "focus_session_planned_event_requires_task",
        "focus_sessions",
        "planned_event_id IS NULL OR task_id IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_focus_sessions_user_task",
        "focus_sessions",
        "tasks",
        ["user_id", "task_id"],
        ["user_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_focus_sessions_planned_work_block",
        "focus_sessions",
        "calendar_events",
        ["user_id", "planned_event_id", "task_id"],
        ["user_id", "id", "source_task_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_focus_sessions_planned_work_block",
        "focus_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_focus_sessions_user_task",
        "focus_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "focus_session_planned_event_requires_task",
        "focus_sessions",
        type_="check",
    )
    op.drop_index("ix_focus_sessions_user_planned_event", table_name="focus_sessions")
    op.drop_index("ix_focus_sessions_user_task", table_name="focus_sessions")
    op.drop_column("focus_sessions", "planned_event_id")
    op.create_foreign_key(
        "focus_sessions_task_id_fkey",
        "focus_sessions",
        "tasks",
        ["task_id"],
        ["id"],
    )

    op.drop_constraint(
        "fk_calendar_events_user_source_task",
        "calendar_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "calendar_event_source_task_internal",
        "calendar_events",
        type_="check",
    )
    op.drop_index("ix_calendar_events_user_source_task", table_name="calendar_events")
    op.drop_constraint(
        "uq_calendar_events_user_id_source_task",
        "calendar_events",
        type_="unique",
    )
    op.create_foreign_key(
        "calendar_events_source_task_id_fkey",
        "calendar_events",
        "tasks",
        ["source_task_id"],
        ["id"],
    )

    op.drop_constraint("uq_tasks_user_id_id", "tasks", type_="unique")
