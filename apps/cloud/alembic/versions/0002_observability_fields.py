"""observability correlation fields

Revision ID: 0002_observability_fields
Revises: 0001_initial
Create Date: 2026-02-25 23:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_observability_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("telemetry_events", sa.Column("session_id", sa.String(), nullable=True))
    op.add_column("telemetry_events", sa.Column("request_id", sa.String(), nullable=True))
    op.add_column("telemetry_events", sa.Column("outbox_pending_count", sa.Integer(), nullable=True))
    op.add_column("telemetry_events", sa.Column("dlq_count", sa.Integer(), nullable=True))
    op.add_column("telemetry_events", sa.Column("last_error_summary", sa.Text(), nullable=True))

    op.create_index("ix_events_request_id", "telemetry_events", ["request_id"], unique=False)
    op.create_index("ix_events_session_id", "telemetry_events", ["session_id"], unique=False)
    op.create_index("ix_events_device_ingested", "telemetry_events", ["device_id", "ingested_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_events_device_ingested", table_name="telemetry_events")
    op.drop_index("ix_events_session_id", table_name="telemetry_events")
    op.drop_index("ix_events_request_id", table_name="telemetry_events")

    op.drop_column("telemetry_events", "last_error_summary")
    op.drop_column("telemetry_events", "dlq_count")
    op.drop_column("telemetry_events", "outbox_pending_count")
    op.drop_column("telemetry_events", "request_id")
    op.drop_column("telemetry_events", "session_id")
