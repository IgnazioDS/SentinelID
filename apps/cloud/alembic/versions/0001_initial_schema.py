"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-25 18:40:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("registered_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_index("ix_devices_device_id", "devices", ["device_id"], unique=False)
    op.create_index("ix_devices_last_seen_desc", "devices", ["last_seen"], unique=False)

    op.create_table(
        "telemetry_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("timestamp", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("reason_codes", sa.Text(), nullable=True),
        sa.Column("liveness_passed", sa.Boolean(), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("session_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("audit_event_hash", sa.String(), nullable=True),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_device_outcome", "telemetry_events", ["device_id", "outcome"], unique=False)
    op.create_index("ix_events_ingested_desc", "telemetry_events", ["ingested_at"], unique=False)
    op.create_index("ix_events_outcome_ingested", "telemetry_events", ["outcome", "ingested_at"], unique=False)
    op.create_index("ix_events_risk_score", "telemetry_events", ["risk_score"], unique=False)
    op.create_index(
        "ix_events_session_duration", "telemetry_events", ["session_duration_seconds"], unique=False
    )
    op.create_index("ix_telemetry_events_device_id", "telemetry_events", ["device_id"], unique=False)
    op.create_index("ix_telemetry_events_event_id", "telemetry_events", ["event_id"], unique=True)
    op.create_index("ix_telemetry_events_event_type", "telemetry_events", ["event_type"], unique=False)
    op.create_index("ix_telemetry_events_id", "telemetry_events", ["id"], unique=False)
    op.create_index("ix_telemetry_events_ingested_at", "telemetry_events", ["ingested_at"], unique=False)
    op.create_index("ix_telemetry_events_outcome", "telemetry_events", ["outcome"], unique=False)
    op.create_index("ix_telemetry_events_timestamp", "telemetry_events", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_telemetry_events_timestamp", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_outcome", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_ingested_at", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_id", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_event_type", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_event_id", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_device_id", table_name="telemetry_events")
    op.drop_index("ix_events_session_duration", table_name="telemetry_events")
    op.drop_index("ix_events_risk_score", table_name="telemetry_events")
    op.drop_index("ix_events_outcome_ingested", table_name="telemetry_events")
    op.drop_index("ix_events_ingested_desc", table_name="telemetry_events")
    op.drop_index("ix_events_device_outcome", table_name="telemetry_events")
    op.drop_table("telemetry_events")

    op.drop_index("ix_devices_last_seen_desc", table_name="devices")
    op.drop_index("ix_devices_device_id", table_name="devices")
    op.drop_table("devices")
