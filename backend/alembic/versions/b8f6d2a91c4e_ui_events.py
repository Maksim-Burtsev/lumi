"""ui events

Revision ID: b8f6d2a91c4e
Revises: f4b7a91c2d3e
Create Date: 2026-06-16 16:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8f6d2a91c4e"
down_revision: str | None = "f4b7a91c2d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ui_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "topics",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ui_events_created", "ui_events", ["created_at"], unique=False)
    op.create_index("ix_ui_events_user_id", "ui_events", ["user_id", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ui_events_user_id", table_name="ui_events")
    op.drop_index("ix_ui_events_created", table_name="ui_events")
    op.drop_table("ui_events")
