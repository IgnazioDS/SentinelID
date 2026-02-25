"""
Admin endpoints for cloud service.
"""
import json
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime

# Use absolute imports for compatibility with uvicorn
import sys
import os
api_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(api_dir)
sys.path.insert(0, parent_dir)

from models import get_db, TelemetryEvent, Device
from api.admin_auth import verify_admin_token
from api.ingest_metrics import get_ingest_metrics

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
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    outbox_pending_count: Optional[int] = None
    dlq_count: Optional[int] = None
    last_error_summary: Optional[str] = None
    audit_event_hash: Optional[str] = None
    ingested_at: datetime

    class Config:
        from_attributes = True


class EventsResponse(BaseModel):
    """Response for events query."""

    events: List[EventResponse]
    total: int
    limit: int
    offset: int
    has_next: bool


class DeviceResponse(BaseModel):
    """Device response."""

    device_id: str
    registered_at: datetime
    last_seen: datetime
    is_active: bool
    event_count: int = 0

    class Config:
        from_attributes = True


class DevicesResponse(BaseModel):
    """Response for devices query."""

    devices: List[DeviceResponse]
    total: int
    limit: int
    offset: int
    has_next: bool


class DeviceHealthResponse(BaseModel):
    device_id: str
    last_seen: datetime
    event_count: int
    outbox_pending_count: Optional[int] = None
    dlq_count: Optional[int] = None
    last_error_summary: Optional[str] = None
    last_request_id: Optional[str] = None
    last_session_id: Optional[str] = None


class StatsResponse(BaseModel):
    """Statistics response."""

    total_devices: int
    active_devices: int
    total_events: int
    allow_count: int
    deny_count: int
    error_count: int
    liveness_failure_rate: float = 0.0
    latency_p50_ms: Optional[float] = None
    latency_p95_ms: Optional[float] = None
    ingest_success_count: int
    ingest_fail_count: int
    events_ingested_count: int
    ingest_window_seconds: int
    risk_distribution: Dict[str, int]
    device_health: List[DeviceHealthResponse]


@router.get("/admin/events", response_model=EventsResponse)
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    device_id: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    admin_token: str = Depends(verify_admin_token),
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
    if request_id:
        query = query.filter(TelemetryEvent.request_id == request_id)
    if session_id:
        query = query.filter(TelemetryEvent.session_id == session_id)

    if outcome:
        query = query.filter(TelemetryEvent.outcome == outcome)

    # Get total count
    total = query.count()

    # Get paginated results (+1 to derive has_next cheaply)
    events = (
        query.order_by(TelemetryEvent.ingested_at.desc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )
    has_next = len(events) > limit
    page_events = events[:limit]

    # Convert to response format
    event_responses = []
    for event in page_events:
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
            session_id=event.session_id,
            request_id=event.request_id,
            outbox_pending_count=event.outbox_pending_count,
            dlq_count=event.dlq_count,
            last_error_summary=event.last_error_summary,
            audit_event_hash=event.audit_event_hash,
            ingested_at=event.ingested_at
        ))

    return EventsResponse(
        events=event_responses,
        total=total,
        limit=limit,
        offset=offset,
        has_next=has_next,
    )


@router.get("/admin/stats", response_model=StatsResponse)
async def get_stats(
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db)
) -> StatsResponse:
    """
    Get cloud service statistics.

    Returns:
        Statistics about devices and events
    """
    total_devices = db.query(Device).count()
    active_devices = db.query(Device).filter(Device.is_active == True).count()
    total_events = db.query(TelemetryEvent).count()

    allow_count = db.query(TelemetryEvent).filter(TelemetryEvent.outcome == "allow").count()
    deny_count = db.query(TelemetryEvent).filter(TelemetryEvent.outcome == "deny").count()
    error_count = db.query(TelemetryEvent).filter(TelemetryEvent.outcome == "error").count()

    # Calculate liveness failure rate
    liveness_failed = db.query(TelemetryEvent).filter(TelemetryEvent.liveness_passed == False).count()
    liveness_failure_rate = (liveness_failed / total_events * 100) if total_events > 0 else 0.0

    # Latency percentiles (session_duration_seconds is stored in seconds)
    latency_values = [
        row[0]
        for row in db.query(TelemetryEvent.session_duration_seconds)
        .filter(TelemetryEvent.session_duration_seconds.isnot(None))
        .all()
    ]
    latency_ms = sorted(float(v) * 1000.0 for v in latency_values if v is not None)

    latency_p50_ms = _percentile(latency_ms, 50.0) if latency_ms else None
    latency_p95_ms = _percentile(latency_ms, 95.0) if latency_ms else None

    # Risk histogram for dashboarding.
    risk_distribution = {"low": 0, "medium": 0, "high": 0}
    risk_rows = (
        db.query(TelemetryEvent.risk_score)
        .filter(TelemetryEvent.risk_score.isnot(None))
        .all()
    )
    for row in risk_rows:
        score = float(row[0])
        if score < 0.45:
            risk_distribution["low"] += 1
        elif score < 0.75:
            risk_distribution["medium"] += 1
        else:
            risk_distribution["high"] += 1

    ingest_metrics = get_ingest_metrics().snapshot(window_seconds=3600)

    counts = (
        db.query(TelemetryEvent.device_id, func.count(TelemetryEvent.id))
        .group_by(TelemetryEvent.device_id)
        .all()
    )
    count_map = {device_id: int(count) for device_id, count in counts}

    latest_subq = (
        db.query(
            TelemetryEvent.device_id.label("device_id"),
            func.max(TelemetryEvent.ingested_at).label("max_ingested_at"),
        )
        .group_by(TelemetryEvent.device_id)
        .subquery()
    )
    latest_rows = (
        db.query(TelemetryEvent)
        .join(
            latest_subq,
            and_(
                TelemetryEvent.device_id == latest_subq.c.device_id,
                TelemetryEvent.ingested_at == latest_subq.c.max_ingested_at,
            ),
        )
        .all()
    )
    latest_map = {row.device_id: row for row in latest_rows}

    device_health: List[DeviceHealthResponse] = []
    for device in db.query(Device).order_by(Device.last_seen.desc()).all():
        latest = latest_map.get(device.device_id)
        device_health.append(
            DeviceHealthResponse(
                device_id=device.device_id,
                last_seen=device.last_seen,
                event_count=count_map.get(device.device_id, 0),
                outbox_pending_count=getattr(latest, "outbox_pending_count", None),
                dlq_count=getattr(latest, "dlq_count", None),
                last_error_summary=getattr(latest, "last_error_summary", None),
                last_request_id=getattr(latest, "request_id", None),
                last_session_id=getattr(latest, "session_id", None),
            )
        )

    return StatsResponse(
        total_devices=total_devices,
        active_devices=active_devices,
        total_events=total_events,
        allow_count=allow_count,
        deny_count=deny_count,
        error_count=error_count,
        liveness_failure_rate=liveness_failure_rate,
        latency_p50_ms=latency_p50_ms,
        latency_p95_ms=latency_p95_ms,
        ingest_success_count=int(ingest_metrics["ingest_success_count"]),
        ingest_fail_count=int(ingest_metrics["ingest_fail_count"]),
        events_ingested_count=int(ingest_metrics["events_ingested_count"]),
        ingest_window_seconds=int(ingest_metrics["ingest_window_seconds"]),
        risk_distribution=risk_distribution,
        device_health=device_health,
    )


@router.get("/admin/devices", response_model=DevicesResponse)
async def get_devices(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db)
) -> DevicesResponse:
    """
    Retrieve registered devices.

    Query Parameters:
    - limit: Number of devices to return (max 1000)
    - offset: Number of devices to skip

    Returns:
        List of devices with metadata
    """
    query = db.query(Device)
    total = query.count()

    devices = query.order_by(Device.last_seen.desc()).offset(offset).limit(limit + 1).all()
    has_next = len(devices) > limit
    page_devices = devices[:limit]

    counts = (
        db.query(TelemetryEvent.device_id, func.count(TelemetryEvent.id))
        .group_by(TelemetryEvent.device_id)
        .all()
    )
    count_map = {device_id: int(count) for device_id, count in counts}

    device_responses = []
    for device in page_devices:
        event_count = count_map.get(device.device_id, 0)
        device_responses.append(DeviceResponse(
            device_id=device.device_id,
            registered_at=device.registered_at,
            last_seen=device.last_seen,
            is_active=device.is_active,
            event_count=event_count,
        ))

    return DevicesResponse(
        devices=device_responses,
        total=total,
        limit=limit,
        offset=offset,
        has_next=has_next,
    )


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    idx = (len(values) - 1) * (percentile / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    if lo == hi:
        return float(values[lo])
    frac = idx - lo
    return float(values[lo] * (1.0 - frac) + values[hi] * frac)
