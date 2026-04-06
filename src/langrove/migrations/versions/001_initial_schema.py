"""Initial schema for Langrove.

Revision ID: 001
Revises:
Create Date: 2026-04-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Assistants
    op.create_table(
        "assistants",
        sa.Column(
            "assistant_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("graph_id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False, server_default=""),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("metadata_", JSONB, nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Assistant versions
    op.create_table(
        "assistant_versions",
        sa.Column(
            "assistant_id",
            UUID,
            sa.ForeignKey("assistants.assistant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("graph_id", sa.Text, nullable=False),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("metadata_", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("assistant_id", "version"),
    )

    # Threads
    op.create_table(
        "threads",
        sa.Column(
            "thread_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("metadata_", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.Text, nullable=False, server_default="idle"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "status IN ('idle', 'busy', 'interrupted', 'error')", name="ck_threads_status"
        ),
    )

    # Runs
    op.create_table(
        "runs",
        sa.Column("run_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "thread_id",
            UUID,
            sa.ForeignKey("threads.thread_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assistant_id", UUID, sa.ForeignKey("assistants.assistant_id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("input", JSONB, nullable=True),
        sa.Column("kwargs", JSONB, nullable=False, server_default="{}"),
        sa.Column("metadata_", JSONB, nullable=False, server_default="{}"),
        sa.Column("multitask_strategy", sa.Text, nullable=False, server_default="reject"),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'error', 'success', 'timeout', 'interrupted')",
            name="ck_runs_status",
        ),
    )
    op.create_index("idx_runs_thread_id", "runs", ["thread_id"])
    op.create_index("idx_runs_status", "runs", ["status"])
    op.create_index("idx_runs_assistant_id", "runs", ["assistant_id"])

    # Store items
    op.create_table(
        "store_items",
        sa.Column("namespace", sa.ARRAY(sa.Text), nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("value", JSONB, nullable=False, server_default="{}"),
        sa.Column("ttl", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("namespace", "key"),
    )

    # Crons
    op.create_table(
        "crons",
        sa.Column("cron_id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assistant_id", UUID, sa.ForeignKey("assistants.assistant_id"), nullable=False),
        sa.Column("thread_id", UUID, sa.ForeignKey("threads.thread_id"), nullable=True),
        sa.Column("schedule", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("metadata_", JSONB, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("next_run_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("crons")
    op.drop_table("store_items")
    op.drop_index("idx_runs_assistant_id", "runs")
    op.drop_index("idx_runs_status", "runs")
    op.drop_index("idx_runs_thread_id", "runs")
    op.drop_table("runs")
    op.drop_table("threads")
    op.drop_table("assistant_versions")
    op.drop_table("assistants")
