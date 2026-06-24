"""focus sessions

Revision ID: 3d7a9c2f1b80
Revises: 7c2d9a0f4b1a
Create Date: 2026-06-24 23:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3d7a9c2f1b80"
down_revision: str | None = "7c2d9a0f4b1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "focus_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("project_snapshot", sa.Text(), nullable=True),
        sa.Column("intention", sa.Text(), nullable=False),
        sa.Column("planned_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("accomplished_text", sa.Text(), nullable=True),
        sa.Column("distraction_text", sa.Text(), nullable=True),
        sa.Column("next_step_text", sa.Text(), nullable=True),
        sa.Column("focus_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="focus_session_status",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_focus_sessions_user_project", "focus_sessions", ["user_id", "project_snapshot"])
    op.create_index("ix_focus_sessions_user_started", "focus_sessions", ["user_id", "started_at"])
    op.create_index("ix_focus_sessions_user_status", "focus_sessions", ["user_id", "status"])
    op.create_index(
        "uq_focus_sessions_one_active",
        "focus_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_focus_sessions_one_active", table_name="focus_sessions", postgresql_where=sa.text("status = 'active'"))
    op.drop_index("ix_focus_sessions_user_status", table_name="focus_sessions")
    op.drop_index("ix_focus_sessions_user_started", table_name="focus_sessions")
    op.drop_index("ix_focus_sessions_user_project", table_name="focus_sessions")
    op.drop_table("focus_sessions")
