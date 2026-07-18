"""persist focus break cycles

Revision ID: d9e4b7a1c205
Revises: a4c8d2e71f6b
Create Date: 2026-07-18 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e4b7a1c205"
down_revision: str | None = "a4c8d2e71f6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("focus_sessions", sa.Column("break_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "focus_sessions",
        sa.Column("break_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "focus_sessions",
        sa.Column("break_target_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "focus_sessions",
        sa.Column("break_ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "focus_session_break_minutes",
        "focus_sessions",
        "break_minutes IS NULL OR break_minutes BETWEEN 1 AND 60",
    )
    op.create_check_constraint(
        "focus_session_break_state",
        "focus_sessions",
        "(break_started_at IS NULL AND break_target_end_at IS NULL "
        "AND break_ended_at IS NULL) OR "
        "(status = 'completed' AND break_minutes IS NOT NULL "
        "AND break_started_at IS NOT NULL "
        "AND break_target_end_at > break_started_at "
        "AND (break_ended_at IS NULL OR break_ended_at >= break_started_at))",
    )
    op.create_index(
        "uq_focus_sessions_one_active_break",
        "focus_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text(
            "break_started_at IS NOT NULL AND break_ended_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_focus_sessions_one_active_break", table_name="focus_sessions")
    op.drop_constraint("focus_session_break_state", "focus_sessions", type_="check")
    op.drop_constraint("focus_session_break_minutes", "focus_sessions", type_="check")
    op.drop_column("focus_sessions", "break_ended_at")
    op.drop_column("focus_sessions", "break_target_end_at")
    op.drop_column("focus_sessions", "break_started_at")
    op.drop_column("focus_sessions", "break_minutes")
