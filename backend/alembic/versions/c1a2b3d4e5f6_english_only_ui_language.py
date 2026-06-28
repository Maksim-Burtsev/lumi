"""english only ui language

Revision ID: c1a2b3d4e5f6
Revises: 9f1d2c3a4b5e
Create Date: 2026-06-28 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: str | None = "9f1d2c3a4b5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        update users
        set
            locale = 'en',
            settings = jsonb_set(
                jsonb_set(
                    jsonb_set(
                        coalesce(settings, '{}'::jsonb),
                        '{locale_source}',
                        '"telegram"'::jsonb,
                        true
                    ),
                    '{reply_language_mode}',
                    '"auto"'::jsonb,
                    true
                ),
                '{reply_language}',
                '"en"'::jsonb,
                true
            )
        """
    )


def downgrade() -> None:
    pass
