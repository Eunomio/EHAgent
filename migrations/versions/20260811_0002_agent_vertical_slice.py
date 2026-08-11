"""Add demo risk tasks and resident feedback.

Revision ID: 20260811_0002
Revises: 20260811_0001
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0002"
down_revision: str | None = "20260811_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create task and idempotent feedback persistence for v0.2.0."""

    op.create_table(
        "risk_task",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("scene_id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("location", sa.String(length=160), nullable=False),
        sa.Column("risk_type", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.String(length=512), nullable=False),
        sa.Column("suggested_action", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("runtime_mode", sa.String(length=32), nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column("evidence_label", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deferred_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_risk_task_task_id", "risk_task", ["task_id"])
    op.create_index("ix_risk_task_scene_id", "risk_task", ["scene_id"])
    op.create_index("ix_risk_task_status", "risk_task", ["status"])
    op.create_index("ix_risk_task_source_type", "risk_task", ["source_type"])
    op.create_index("ix_risk_task_runtime_mode", "risk_task", ["runtime_mode"])

    op.create_table(
        "task_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feedback_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("result_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["risk_task.task_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feedback_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_task_feedback_task_id", "task_feedback", ["task_id"])


def downgrade() -> None:
    """Remove task and feedback persistence."""

    op.drop_index("ix_task_feedback_task_id", table_name="task_feedback")
    op.drop_table("task_feedback")
    op.drop_index("ix_risk_task_runtime_mode", table_name="risk_task")
    op.drop_index("ix_risk_task_source_type", table_name="risk_task")
    op.drop_index("ix_risk_task_status", table_name="risk_task")
    op.drop_index("ix_risk_task_scene_id", table_name="risk_task")
    op.drop_index("ix_risk_task_task_id", table_name="risk_task")
    op.drop_table("risk_task")
