"""
Admin endpoints for cloud service.
"""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

# Use absolute imports for compatibility with uvicorn
import sys
import os
api_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(api_dir)
sys.path.insert(0, parent_dir)

from models import get_db, TelemetryEvent

router = APIRouter(tags=["Admin"])


class EventResponse(BaseModel):
    """Telemetry event response."""

    event_id: str
    device_id: str
    timestamp: int
    event_type: str
    outcome: str
    reason_codes: List[str]
    liveness_passed: Optional[bool] = None
    similarity_score: Optional[float] = None
    risk_score: Optional[float] = None
    session_duration_seconds: Optional[int] = None
    audit_event_hash: Optional[str] = None
    ingested_at: datetime

    class Config:
        from_attributes = True


class EventsResponse(BaseModel):
    """Response for events query."""

    events: List[EventResponse]
    total: int


@router.get("/admin/events", response_model=EventsResponse)
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    device_id: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    db: Session = Depends(get_db)
) -> EventsResponse:
    """
    Retrieve telemetry events from cloud.

    Query Parameters:
    - limit: Number of events to return (max 1000)
    - offset: Number of events to skip
    - device_id: Filter by device ID (optional)
    - outcome: Filter by outcome (allow/deny/error) (optional)

    Returns:
        List of telemetry events with total count
    """
    query = db.query(TelemetryEvent)

    # Apply filters
    if device_id:
        query = query.filter(TelemetryEvent.device_id == device_id)

    if outcome:
        query = query.filter(TelemetryEvent.outcome == outcome)

    # Get total count
    total = query.count()

    # Get paginated results
    events = query.order_by(TelemetryEvent.ingested_at.desc()).offset(offset).limit(limit).all()

    # Convert to response format
    event_responses = []
    for event in events:
        event_responses.append(EventResponse(
            event_id=event.event_id,
            device_id=event.device_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            outcome=event.outcome,
            reason_codes=json.loads(event.reason_codes) if event.reason_codes else [],
            liveness_passed=event.liveness_passed,
            similarity_score=event.similarity_score,
            risk_score=event.risk_score,
            session_duration_seconds=event.session_duration_seconds,
            audit_event_hash=event.audit_event_hash,
            ingested_at=event.ingested_at
        ))

    return EventsResponse(events=event_responses, total=total)


@router.get("/admin/stats")
async def get_stats(db: Session = Depends(get_db)):
    """
    Get cloud service statistics.

    Returns:
        Statistics about devices and events
    """
    from ..models import Device

    total_devices = db.query(Device).count()
    active_devices = db.query(Device).filter(Device.is_active == True).count()
    total_events = db.query(TelemetryEvent).count()

    allow_count = db.query(TelemetryEvent).filter(TelemetryEvent.outcome == "allow").count()
    deny_count = db.query(TelemetryEvent).filter(TelemetryEvent.outcome == "deny").count()
    error_count = db.query(TelemetryEvent).filter(TelemetryEvent.outcome == "error").count()

    return {
        "total_devices": total_devices,
        "active_devices": active_devices,
        "total_events": total_events,
        "allow_count": allow_count,
        "deny_count": deny_count,
        "error_count": error_count,
    }
