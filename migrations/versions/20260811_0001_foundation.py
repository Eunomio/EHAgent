"""Create foundational runtime, observation and audit tables.

Revision ID: 20260811_0001
Revises: None
Create Date: 2026-08-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260811_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the v0.1.0 foundational schema."""

    op.create_table(
        "runtime_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("changed_by", sa.String(length=128), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "observation_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("scene_id", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("runtime_mode", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_observation_event_event_id", "observation_event", ["event_id"])
    op.create_index("ix_observation_event_trace_id", "observation_event", ["trace_id"])
    op.create_index("ix_observation_event_event_type", "observation_event", ["event_type"])
    op.create_index("ix_observation_event_scene_id", "observation_event", ["scene_id"])
    op.create_index("ix_observation_event_source_type", "observation_event", ["source_type"])
    op.create_index("ix_observation_event_runtime_mode", "observation_event", ["runtime_mode"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=128), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    """Remove the v0.1.0 foundational schema."""

    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_observation_event_runtime_mode", table_name="observation_event")
    op.drop_index("ix_observation_event_source_type", table_name="observation_event")
    op.drop_index("ix_observation_event_scene_id", table_name="observation_event")
    op.drop_index("ix_observation_event_event_type", table_name="observation_event")
    op.drop_index("ix_observation_event_trace_id", table_name="observation_event")
    op.drop_index("ix_observation_event_event_id", table_name="observation_event")
    op.drop_table("observation_event")
    op.drop_table("runtime_state")
