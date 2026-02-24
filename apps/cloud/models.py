"""
Database models for cloud telemetry storage.
"""
import os
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime


# Database setup
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://admin:password@localhost:5432/sentinelid"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Device(Base):
    """Registered device with public key."""

    __tablename__ = "devices"

    device_id = Column(String, primary_key=True, index=True)
    public_key = Column(Text, nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    telemetry_events = relationship("TelemetryEvent", back_populates="device")

    __table_args__ = (
        Index("ix_devices_last_seen_desc", "last_seen"),
    )


class TelemetryEvent(Base):
    """Ingested telemetry event from edge device."""

    __tablename__ = "telemetry_events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True)
    device_id = Column(String, ForeignKey("devices.device_id"), index=True)
    timestamp = Column(Integer, index=True)
    event_type = Column(String, index=True)  # "auth_started", "auth_finished"
    outcome = Column(String, index=True)  # "allow", "deny", "error"
    reason_codes = Column(Text)  # JSON array
    liveness_passed = Column(Boolean, nullable=True)
    similarity_score = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    session_duration_seconds = Column(Integer, nullable=True)
    audit_event_hash = Column(String, nullable=True)
    signature = Column(Text, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow, index=True)

    device = relationship("Device", back_populates="telemetry_events")

    __table_args__ = (
        Index("ix_events_ingested_desc", "ingested_at"),
        Index("ix_events_device_outcome", "device_id", "outcome"),
        Index("ix_events_outcome_ingested", "outcome", "ingested_at"),
        Index("ix_events_risk_score", "risk_score"),
        Index("ix_events_session_duration", "session_duration_seconds"),
    )


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
