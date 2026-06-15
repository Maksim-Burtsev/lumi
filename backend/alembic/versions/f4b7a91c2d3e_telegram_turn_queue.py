"""telegram turn queue

Revision ID: f4b7a91c2d3e
Revises: e0a64c15d333
Create Date: 2026-06-15 15:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4b7a91c2d3e"
down_revision: str | None = "e0a64c15d333"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_updates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("update_id"),
    )
    op.create_index(
        "ix_telegram_updates_chat_message",
        "telegram_updates",
        ["telegram_chat_id", "telegram_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_updates_user_created",
        "telegram_updates",
        ["telegram_user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "assistant_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sequence_no", sa.BigInteger(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("primary_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "source_update_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "source_message_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status_message_id", sa.BigInteger(), nullable=True),
        sa.Column("debounce_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sequence_no", name="uq_assistant_turns_user_sequence"),
    )
    op.create_index(
        "ix_assistant_turns_status_deadline",
        "assistant_turns",
        ["status", "debounce_deadline_at"],
        unique=False,
    )
    op.create_index(
        "ix_assistant_turns_user_status_sequence",
        "assistant_turns",
        ["user_id", "status", "sequence_no"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_turns_user_status_sequence", table_name="assistant_turns")
    op.drop_index("ix_assistant_turns_status_deadline", table_name="assistant_turns")
    op.drop_table("assistant_turns")
    op.drop_index("ix_telegram_updates_user_created", table_name="telegram_updates")
    op.drop_index("ix_telegram_updates_chat_message", table_name="telegram_updates")
    op.drop_table("telegram_updates")
