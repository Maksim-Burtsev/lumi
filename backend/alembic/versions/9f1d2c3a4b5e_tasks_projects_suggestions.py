"""tasks projects suggestions

Revision ID: 9f1d2c3a4b5e
Revises: 7c2d9a0f4b1a
Create Date: 2026-06-21 22:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9f1d2c3a4b5e"
down_revision: str | None = "7c2d9a0f4b1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "archived", name="project_status", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "normalized_name", name="uq_projects_user_normalized_name"),
    )
    op.create_index("ix_projects_user_status", "projects", ["user_id", "status"], unique=False)

    op.add_column("tasks", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.add_column("tasks", sa.Column("target_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("estimated_minutes", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("estimate_source", sa.Text(), nullable=True))
    op.create_foreign_key("fk_tasks_project_id_projects", "tasks", "projects", ["project_id"], ["id"])
    op.create_index("ix_tasks_user_project_status", "tasks", ["user_id", "project_id", "status"], unique=False)

    op.execute(
        """
        insert into projects (id, user_id, name, normalized_name, status, created_at, updated_at, metadata)
        select gen_random_uuid(), user_id, trimmed_project, lower(trimmed_project), 'active', now(), now(), '{}'::jsonb
        from (
            select distinct user_id, btrim(project) as trimmed_project
            from tasks
            where project is not null and btrim(project) <> ''
        ) source
        on conflict (user_id, normalized_name) do nothing
        """
    )
    op.execute(
        """
        update tasks
        set project_id = projects.id
        from projects
        where tasks.user_id = projects.user_id
          and tasks.project is not null
          and lower(btrim(tasks.project)) = projects.normalized_name
        """
    )

    op.create_table(
        "assistant_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "accepted",
                "dismissed",
                "expired",
                name="assistant_suggestion_status",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "affected_task_ids",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("context_hash", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assistant_suggestions_context",
        "assistant_suggestions",
        ["user_id", "context_hash"],
        unique=False,
    )
    op.create_index(
        "ix_assistant_suggestions_user_kind",
        "assistant_suggestions",
        ["user_id", "kind", "status"],
        unique=False,
    )
    op.create_index(
        "ix_assistant_suggestions_user_status",
        "assistant_suggestions",
        ["user_id", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "assistant_opportunity_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("context_hash", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("debounce_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "scope_key", name="uq_assistant_jobs_user_kind_scope"),
    )
    op.create_index(
        "ix_assistant_jobs_due",
        "assistant_opportunity_jobs",
        ["next_check_at", "locked_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_jobs_due", table_name="assistant_opportunity_jobs")
    op.drop_table("assistant_opportunity_jobs")
    op.drop_index("ix_assistant_suggestions_user_status", table_name="assistant_suggestions")
    op.drop_index("ix_assistant_suggestions_user_kind", table_name="assistant_suggestions")
    op.drop_index("ix_assistant_suggestions_context", table_name="assistant_suggestions")
    op.drop_table("assistant_suggestions")
    op.drop_index("ix_tasks_user_project_status", table_name="tasks")
    op.drop_constraint("fk_tasks_project_id_projects", "tasks", type_="foreignkey")
    op.drop_column("tasks", "estimate_source")
    op.drop_column("tasks", "estimated_minutes")
    op.drop_column("tasks", "target_at")
    op.drop_column("tasks", "project_id")
    op.drop_index("ix_projects_user_status", table_name="projects")
    op.drop_table("projects")
