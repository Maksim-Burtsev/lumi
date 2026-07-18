"""add versioned reflection extraction

Revision ID: f2a7c4d91e30
Revises: a14b9c27d530
Create Date: 2026-07-18 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a7c4d91e30"
down_revision: str | None = "a14b9c27d530"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "focus_sessions",
        sa.Column("reflection_outcome", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "focus_sessions",
        sa.Column("reflection_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "focus_sessions",
        sa.Column("reflection_input_hash", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "focus_session_reflection_outcome_values",
        "focus_sessions",
        "reflection_outcome IS NULL OR reflection_outcome IN ('done', 'progress', 'blocked')",
    )
    op.create_unique_constraint(
        "uq_focus_sessions_user_id_id",
        "focus_sessions",
        ["user_id", "id"],
    )

    op.create_table(
        "focus_session_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("focus_session_id", sa.Uuid(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column(
            "source_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("raw_text_snapshot", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("outcome_source", sa.Text(), nullable=True),
        sa.Column("outcome_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("work_type", sa.Text(), nullable=True),
        sa.Column("work_type_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column(
            "frictions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("normalized_next_action", sa.Text(), nullable=True),
        sa.Column("next_action_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'ready', 'failed', 'superseded')",
            name="focus_session_analysis_status_values",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('done', 'progress', 'blocked')",
            name="focus_session_analysis_outcome_values",
        ),
        sa.CheckConstraint(
            "work_type IS NULL OR work_type IN "
            "('deep_work', 'admin', 'communication', 'planning', 'learning', 'creative', 'other')",
            name="focus_session_analysis_work_type_values",
        ),
        sa.CheckConstraint(
            "outcome_confidence IS NULL OR outcome_confidence BETWEEN 0 AND 1",
            name="focus_session_analysis_outcome_confidence",
        ),
        sa.CheckConstraint(
            "work_type_confidence IS NULL OR work_type_confidence BETWEEN 0 AND 1",
            name="focus_session_analysis_work_type_confidence",
        ),
        sa.CheckConstraint(
            "next_action_confidence IS NULL OR next_action_confidence BETWEEN 0 AND 1",
            name="focus_session_analysis_next_action_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "focus_session_id"],
            ["focus_sessions.user_id", "focus_sessions.id"],
            name="fk_focus_session_analyses_user_session",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "focus_session_id",
            "input_hash",
            "schema_version",
            "prompt_version",
            "model_provider",
            "model_name",
            name="uq_focus_session_analysis_version",
        ),
    )
    op.create_index(
        "ix_focus_session_analyses_user_status",
        "focus_session_analyses",
        ["user_id", "status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_focus_session_analyses_session_created",
        "focus_session_analyses",
        ["focus_session_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_focus_session_analyses_session_created",
        table_name="focus_session_analyses",
    )
    op.drop_index(
        "ix_focus_session_analyses_user_status",
        table_name="focus_session_analyses",
    )
    op.drop_table("focus_session_analyses")
    op.drop_constraint(
        "uq_focus_sessions_user_id_id",
        "focus_sessions",
        type_="unique",
    )
    op.drop_constraint(
        "focus_session_reflection_outcome_values",
        "focus_sessions",
        type_="check",
    )
    op.drop_column("focus_sessions", "reflection_input_hash")
    op.drop_column("focus_sessions", "reflection_text")
    op.drop_column("focus_sessions", "reflection_outcome")
