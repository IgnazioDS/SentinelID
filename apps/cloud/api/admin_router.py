"""
Admin endpoints for cloud service.
"""
from __future__ import annotations

import io
import json
import os
import platform
import tarfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

# Use absolute imports for compatibility with uvicorn
import sys
api_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(api_dir)
sys.path.insert(0, parent_dir)

from models import get_db, TelemetryEvent, Device
from api.admin_auth import verify_admin_token
from api.ingest_metrics import get_ingest_metrics

router = APIRouter(tags=["Admin"])

_WINDOW_SECONDS = {
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
}

_REDACT_KEYS = {
    "authorization",
    "token",
    "admin_token",
    "edge_auth_token",
    "signature",
    "batch_signature",
    "device_public_key",
    "frame",
    "frames",
    "image",
    "images",
    "embedding",
    "embeddings",
}


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
    outbox_pending_count: Optional[int] = None
    dlq_count: Optional[int] = None
    last_error_summary: Optional[str] = None
    last_request_id: Optional[str] = None
    last_session_id: Optional[str] = None

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

    window: str
    window_seconds: int
    window_started_at: datetime
    total_devices: int
    active_devices: int
    active_devices_window: int
    total_events: int
    window_events: int
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
    outbox_pending_total: int
    dlq_total: int
    device_health: List[DeviceHealthResponse]


class EventSeriesPoint(BaseModel):
    bucket_start: datetime
    events: int
    allow: int
    deny: int
    error: int
    outbox_pending_avg: Optional[float] = None
    dlq_avg: Optional[float] = None


class EventSeriesResponse(BaseModel):
    window: str
    bucket: str
    start: datetime
    end: datetime
    total_events: int
    outcome_breakdown: Dict[str, int]
    points: List[EventSeriesPoint]


class DeviceDetailResponse(BaseModel):
    device: DeviceResponse
    recent_events: List[EventResponse]
    outcome_breakdown: Dict[str, int]


def _window_to_seconds(window: str) -> int:
    return _WINDOW_SECONDS.get(window, _WINDOW_SECONDS["24h"])


def _ts_to_datetime(value: Optional[int]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.utcfromtimestamp(value)


def _datetime_floor(value: datetime, bucket: str) -> datetime:
    if bucket == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _bucket_delta(bucket: str) -> timedelta:
    return timedelta(hours=1) if bucket == "hour" else timedelta(days=1)


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


def _event_to_response(event: TelemetryEvent) -> EventResponse:
    return EventResponse(
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
        ingested_at=event.ingested_at,
    )


def _sanitize_payload(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in _REDACT_KEYS or "token" in lowered or "signature" in lowered:
                out[key] = "[REDACTED]"
            else:
                out[key] = _sanitize_payload(item)
        return out
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str) and value.lower().startswith("bearer "):
        return "Bearer [REDACTED]"
    return value


def _build_latest_map(db: Session):
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
    return {row.device_id: row for row in latest_rows}


def _build_stats(db: Session, window: str) -> StatsResponse:
    now = datetime.utcnow()
    window_seconds = _window_to_seconds(window)
    window_started_at = now - timedelta(seconds=window_seconds)

    total_devices = db.query(Device).count()
    active_devices = db.query(Device).filter(Device.is_active.is_(True)).count()
    total_events = db.query(TelemetryEvent).count()

    window_query = db.query(TelemetryEvent).filter(TelemetryEvent.ingested_at >= window_started_at)
    window_events = window_query.count()

    allow_count = window_query.filter(TelemetryEvent.outcome == "allow").count()
    deny_count = window_query.filter(TelemetryEvent.outcome == "deny").count()
    error_count = window_query.filter(TelemetryEvent.outcome == "error").count()

    liveness_failed = window_query.filter(TelemetryEvent.liveness_passed.is_(False)).count()
    liveness_failure_rate = (liveness_failed / window_events * 100) if window_events > 0 else 0.0

    latency_values = [
        row[0]
        for row in window_query.with_entities(TelemetryEvent.session_duration_seconds)
        .filter(TelemetryEvent.session_duration_seconds.isnot(None))
        .all()
    ]
    latency_ms = sorted(float(v) * 1000.0 for v in latency_values if v is not None)
    latency_p50_ms = _percentile(latency_ms, 50.0) if latency_ms else None
    latency_p95_ms = _percentile(latency_ms, 95.0) if latency_ms else None

    risk_distribution = {"low": 0, "medium": 0, "high": 0}
    risk_rows = (
        window_query.with_entities(TelemetryEvent.risk_score)
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

    counts = (
        db.query(TelemetryEvent.device_id, func.count(TelemetryEvent.id))
        .group_by(TelemetryEvent.device_id)
        .all()
    )
    count_map = {device_id: int(count) for device_id, count in counts}
    latest_map = _build_latest_map(db)

    outbox_pending_total = 0
    dlq_total = 0
    device_health: List[DeviceHealthResponse] = []
    for device in db.query(Device).order_by(Device.last_seen.desc()).all():
        latest = latest_map.get(device.device_id)
        outbox_pending = int(getattr(latest, "outbox_pending_count", 0) or 0)
        dlq = int(getattr(latest, "dlq_count", 0) or 0)
        outbox_pending_total += outbox_pending
        dlq_total += dlq
        device_health.append(
            DeviceHealthResponse(
                device_id=device.device_id,
                last_seen=device.last_seen,
                event_count=count_map.get(device.device_id, 0),
                outbox_pending_count=outbox_pending,
                dlq_count=dlq,
                last_error_summary=getattr(latest, "last_error_summary", None),
                last_request_id=getattr(latest, "request_id", None),
                last_session_id=getattr(latest, "session_id", None),
            )
        )

    active_devices_window = int(
        db.query(func.count(func.distinct(TelemetryEvent.device_id)))
        .filter(TelemetryEvent.ingested_at >= window_started_at)
        .scalar()
        or 0
    )

    ingest_metrics = get_ingest_metrics().snapshot(window_seconds=window_seconds)

    return StatsResponse(
        window=window,
        window_seconds=window_seconds,
        window_started_at=window_started_at,
        total_devices=total_devices,
        active_devices=active_devices,
        active_devices_window=active_devices_window,
        total_events=total_events,
        window_events=window_events,
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
        outbox_pending_total=outbox_pending_total,
        dlq_total=dlq_total,
        device_health=device_health,
    )


@router.get("/admin/events", response_model=EventsResponse)
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    device_id: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    reason_code: Optional[str] = Query(None),
    start_ts: Optional[int] = Query(None),
    end_ts: Optional[int] = Query(None),
    q: Optional[str] = Query(None),
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
) -> EventsResponse:
    """Retrieve telemetry events from cloud with filtering and pagination."""
    _ = admin_token
    query = db.query(TelemetryEvent)

    if device_id:
        query = query.filter(TelemetryEvent.device_id == device_id)
    if request_id:
        query = query.filter(TelemetryEvent.request_id == request_id)
    if session_id:
        query = query.filter(TelemetryEvent.session_id == session_id)
    if outcome:
        query = query.filter(TelemetryEvent.outcome == outcome)
    if reason_code:
        query = query.filter(TelemetryEvent.reason_codes.like(f'%"{reason_code}"%'))

    start_dt = _ts_to_datetime(start_ts)
    end_dt = _ts_to_datetime(end_ts)
    if start_dt:
        query = query.filter(TelemetryEvent.ingested_at >= start_dt)
    if end_dt:
        query = query.filter(TelemetryEvent.ingested_at <= end_dt)

    if q:
        like_q = f"%{q}%"
        query = query.filter(
            or_(
                TelemetryEvent.event_id.ilike(like_q),
                TelemetryEvent.device_id.ilike(like_q),
                TelemetryEvent.request_id.ilike(like_q),
                TelemetryEvent.session_id.ilike(like_q),
                TelemetryEvent.reason_codes.ilike(like_q),
            )
        )

    total = query.count()
    events = (
        query.order_by(TelemetryEvent.ingested_at.desc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )
    has_next = len(events) > limit
    page_events = events[:limit]

    return EventsResponse(
        events=[_event_to_response(event) for event in page_events],
        total=total,
        limit=limit,
        offset=offset,
        has_next=has_next,
    )


@router.get("/admin/events/series", response_model=EventSeriesResponse)
async def get_events_series(
    window: str = Query("24h", pattern="^(24h|7d|30d)$"),
    device_id: Optional[str] = Query(None),
    start_ts: Optional[int] = Query(None),
    end_ts: Optional[int] = Query(None),
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
) -> EventSeriesResponse:
    """Return a chart-ready event series with outcome and lag trends."""
    _ = admin_token
    now = datetime.utcnow()
    default_start = now - timedelta(seconds=_window_to_seconds(window))
    start_dt = _ts_to_datetime(start_ts) or default_start
    end_dt = _ts_to_datetime(end_ts) or now

    window_span = (end_dt - start_dt).total_seconds()
    bucket = "hour" if window_span <= (48 * 3600) else "day"

    query = db.query(TelemetryEvent).filter(
        TelemetryEvent.ingested_at >= start_dt,
        TelemetryEvent.ingested_at <= end_dt,
    )
    if device_id:
        query = query.filter(TelemetryEvent.device_id == device_id)

    rows = query.order_by(TelemetryEvent.ingested_at.asc()).all()

    points: Dict[datetime, Dict[str, float]] = {}
    cursor = _datetime_floor(start_dt, bucket)
    end_bucket = _datetime_floor(end_dt, bucket)
    while cursor <= end_bucket:
        points[cursor] = {
            "events": 0,
            "allow": 0,
            "deny": 0,
            "error": 0,
            "outbox_sum": 0.0,
            "outbox_count": 0,
            "dlq_sum": 0.0,
            "dlq_count": 0,
        }
        cursor += _bucket_delta(bucket)

    outcome_breakdown = {"allow": 0, "deny": 0, "error": 0}

    for row in rows:
        key = _datetime_floor(row.ingested_at, bucket)
        if key not in points:
            points[key] = {
                "events": 0,
                "allow": 0,
                "deny": 0,
                "error": 0,
                "outbox_sum": 0.0,
                "outbox_count": 0,
                "dlq_sum": 0.0,
                "dlq_count": 0,
            }
        point = points[key]
        point["events"] += 1

        outcome = row.outcome if row.outcome in outcome_breakdown else "error"
        point[outcome] += 1
        outcome_breakdown[outcome] += 1

        if row.outbox_pending_count is not None:
            point["outbox_sum"] += float(row.outbox_pending_count)
            point["outbox_count"] += 1
        if row.dlq_count is not None:
            point["dlq_sum"] += float(row.dlq_count)
            point["dlq_count"] += 1

    series_points: List[EventSeriesPoint] = []
    for key in sorted(points.keys()):
        point = points[key]
        outbox_avg = None
        dlq_avg = None
        if point["outbox_count"] > 0:
            outbox_avg = round(point["outbox_sum"] / point["outbox_count"], 3)
        if point["dlq_count"] > 0:
            dlq_avg = round(point["dlq_sum"] / point["dlq_count"], 3)
        series_points.append(
            EventSeriesPoint(
                bucket_start=key,
                events=int(point["events"]),
                allow=int(point["allow"]),
                deny=int(point["deny"]),
                error=int(point["error"]),
                outbox_pending_avg=outbox_avg,
                dlq_avg=dlq_avg,
            )
        )

    return EventSeriesResponse(
        window=window,
        bucket=bucket,
        start=start_dt,
        end=end_dt,
        total_events=len(rows),
        outcome_breakdown=outcome_breakdown,
        points=series_points,
    )


@router.get("/admin/stats", response_model=StatsResponse)
async def get_stats(
    window: str = Query("24h", pattern="^(24h|7d|30d)$"),
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
) -> StatsResponse:
    """Get cloud service statistics for the selected time window."""
    _ = admin_token
    return _build_stats(db, window)


@router.get("/admin/devices", response_model=DevicesResponse)
async def get_devices(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
) -> DevicesResponse:
    """Retrieve registered devices with reliability fields."""
    _ = admin_token
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
    latest_map = _build_latest_map(db)

    device_responses = []
    for device in page_devices:
        latest = latest_map.get(device.device_id)
        device_responses.append(
            DeviceResponse(
                device_id=device.device_id,
                registered_at=device.registered_at,
                last_seen=device.last_seen,
                is_active=device.is_active,
                event_count=count_map.get(device.device_id, 0),
                outbox_pending_count=getattr(latest, "outbox_pending_count", None),
                dlq_count=getattr(latest, "dlq_count", None),
                last_error_summary=getattr(latest, "last_error_summary", None),
                last_request_id=getattr(latest, "request_id", None),
                last_session_id=getattr(latest, "session_id", None),
            )
        )

    return DevicesResponse(
        devices=device_responses,
        total=total,
        limit=limit,
        offset=offset,
        has_next=has_next,
    )


@router.get("/admin/devices/{device_id}", response_model=DeviceDetailResponse)
async def get_device_detail(
    device_id: str,
    limit: int = Query(50, ge=1, le=200),
    start_ts: Optional[int] = Query(None),
    end_ts: Optional[int] = Query(None),
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
) -> DeviceDetailResponse:
    """Return per-device reliability and recent event detail."""
    _ = admin_token
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    base_query = db.query(TelemetryEvent).filter(TelemetryEvent.device_id == device_id)

    start_dt = _ts_to_datetime(start_ts)
    end_dt = _ts_to_datetime(end_ts)
    if start_dt:
        base_query = base_query.filter(TelemetryEvent.ingested_at >= start_dt)
    if end_dt:
        base_query = base_query.filter(TelemetryEvent.ingested_at <= end_dt)

    recent_events = base_query.order_by(TelemetryEvent.ingested_at.desc()).limit(limit).all()

    total_event_count = int(
        db.query(func.count(TelemetryEvent.id))
        .filter(TelemetryEvent.device_id == device_id)
        .scalar()
        or 0
    )

    latest_event = (
        db.query(TelemetryEvent)
        .filter(TelemetryEvent.device_id == device_id)
        .order_by(TelemetryEvent.ingested_at.desc())
        .first()
    )

    outcome_breakdown = {
        "allow": int(base_query.filter(TelemetryEvent.outcome == "allow").count()),
        "deny": int(base_query.filter(TelemetryEvent.outcome == "deny").count()),
        "error": int(base_query.filter(TelemetryEvent.outcome == "error").count()),
    }

    device_payload = DeviceResponse(
        device_id=device.device_id,
        registered_at=device.registered_at,
        last_seen=device.last_seen,
        is_active=device.is_active,
        event_count=total_event_count,
        outbox_pending_count=getattr(latest_event, "outbox_pending_count", None),
        dlq_count=getattr(latest_event, "dlq_count", None),
        last_error_summary=getattr(latest_event, "last_error_summary", None),
        last_request_id=getattr(latest_event, "request_id", None),
        last_session_id=getattr(latest_event, "session_id", None),
    )

    return DeviceDetailResponse(
        device=device_payload,
        recent_events=[_event_to_response(event) for event in recent_events],
        outcome_breakdown=outcome_breakdown,
    )


@router.post("/admin/support-bundle")
async def generate_support_bundle(
    window: str = Query("24h", pattern="^(24h|7d|30d)$"),
    events_limit: int = Query(100, ge=10, le=500),
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
):
    """Generate a sanitized support bundle and stream it as tar.gz."""
    _ = admin_token

    stats = _build_stats(db, window)
    events = (
        db.query(TelemetryEvent)
        .order_by(TelemetryEvent.ingested_at.desc())
        .limit(events_limit)
        .all()
    )
    devices = (
        db.query(Device)
        .order_by(Device.last_seen.desc())
        .limit(200)
        .all()
    )

    created_at = datetime.utcnow().replace(microsecond=0)
    bundle_name_ts = created_at.strftime("%Y%m%dT%H%M%SZ")

    payloads = {
        "stats.json": stats.model_dump(mode="json"),
        "events.json": {"events": [_event_to_response(event).model_dump(mode="json") for event in events]},
        "devices.json": {
            "devices": [
                {
                    "device_id": device.device_id,
                    "registered_at": device.registered_at.isoformat(),
                    "last_seen": device.last_seen.isoformat(),
                    "is_active": bool(device.is_active),
                }
                for device in devices
            ]
        },
        "environment.json": {
            "service": "sentinelid-cloud",
            "generated_at": created_at.isoformat() + "Z",
            "window": window,
            "events_limit": events_limit,
            "python": platform.python_version(),
        },
    }

    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        for filename, payload in payloads.items():
            sanitized = _sanitize_payload(payload)
            raw = json.dumps(sanitized, indent=2, sort_keys=True).encode("utf-8")
            info = tarfile.TarInfo(name=filename)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))

    bundle_buffer.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="support_bundle_{bundle_name_ts}.tar.gz"',
        "X-Support-Bundle-Created-At": created_at.isoformat() + "Z",
    }

    return StreamingResponse(bundle_buffer, media_type="application/gzip", headers=headers)
