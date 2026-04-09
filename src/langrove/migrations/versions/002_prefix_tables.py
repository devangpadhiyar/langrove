"""Rename all tables with langrove_ prefix to avoid clashes in shared databases.

Revision ID: 002
Revises: 001
Create Date: 2026-04-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RENAMES = [
    ("assistants", "langrove_assistants"),
    ("assistant_versions", "langrove_assistant_versions"),
    ("threads", "langrove_threads"),
    ("runs", "langrove_runs"),
    ("store_items", "langrove_store_items"),
    ("crons", "langrove_crons"),
]

# Indexes created in 001 that reference old table names
_INDEX_RENAMES = [
    ("idx_runs_thread_id", "langrove_runs", "langrove_idx_runs_thread_id"),
    ("idx_runs_status", "langrove_runs", "langrove_idx_runs_status"),
    ("idx_runs_assistant_id", "langrove_runs", "langrove_idx_runs_assistant_id"),
]

# Check constraints that embed the old table name
_CONSTRAINT_RENAMES = [
    (
        "langrove_threads",
        "ck_threads_status",
        "ck_langrove_threads_status",
        "status IN ('idle', 'busy', 'interrupted', 'error')",
    ),
    (
        "langrove_runs",
        "ck_runs_status",
        "ck_langrove_runs_status",
        "status IN ('pending', 'running', 'error', 'success', 'timeout', 'interrupted')",
    ),
]


def upgrade() -> None:
    # Rename tables
    for old, new in _RENAMES:
        op.rename_table(old, new)

    # Rename indexes (drop old name, create under new name)
    for old_idx, table, _new_idx in _INDEX_RENAMES:
        op.drop_index(old_idx, table_name=table)

    op.create_index("langrove_idx_runs_thread_id", "langrove_runs", ["thread_id"])
    op.create_index("langrove_idx_runs_status", "langrove_runs", ["status"])
    op.create_index("langrove_idx_runs_assistant_id", "langrove_runs", ["assistant_id"])

    # Rename check constraints
    for table, old_ck, new_ck, expr in _CONSTRAINT_RENAMES:
        op.drop_constraint(old_ck, table)
        op.create_check_constraint(new_ck, table, expr)


def downgrade() -> None:
    # Restore check constraints
    for table, old_ck, new_ck, expr in reversed(_CONSTRAINT_RENAMES):
        op.drop_constraint(new_ck, table)
        op.create_check_constraint(old_ck, table, expr)

    # Restore indexes
    op.drop_index("langrove_idx_runs_thread_id", table_name="langrove_runs")
    op.drop_index("langrove_idx_runs_status", table_name="langrove_runs")
    op.drop_index("langrove_idx_runs_assistant_id", table_name="langrove_runs")

    for old_idx, table, _new_idx in _INDEX_RENAMES:
        op.create_index(old_idx, table, [old_idx.split("_")[-1]])

    # Rename tables back
    for old, new in reversed(_RENAMES):
        op.rename_table(new, old)
