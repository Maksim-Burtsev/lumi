"""add evidence-backed focus insights

Revision ID: fe8c1d4a72b6
Revises: f2a7c4d91e30
Create Date: 2026-07-18 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fe8c1d4a72b6"
down_revision: str | None = "f2a7c4d91e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "focus_insights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("support_count", sa.Integer(), nullable=False),
        sa.Column("distinct_days", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column(
            "supporting_session_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("context_hash", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('proposed', 'confirmed', 'dismissed', 'expired')",
            name="focus_insight_status_values",
        ),
        sa.CheckConstraint(
            "support_count >= 3",
            name="focus_insight_support_count_minimum",
        ),
        sa.CheckConstraint(
            "distinct_days >= 2",
            name="focus_insight_distinct_days_minimum",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="focus_insight_confidence",
        ),
        sa.CheckConstraint(
            "window_end > window_start",
            name="focus_insight_window_order",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "kind",
            "window_start",
            "window_end",
            "context_hash",
            name="uq_focus_insight_context",
        ),
    )
    op.create_index(
        "ix_focus_insights_user_status_seen",
        "focus_insights",
        ["user_id", "status", "last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_focus_insights_user_status_seen",
        table_name="focus_insights",
    )
    op.drop_table("focus_insights")
