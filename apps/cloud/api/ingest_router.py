"""
Telemetry event ingest endpoint for edge devices.
"""
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from ..models import get_db, Device, TelemetryEvent
from .signature_verifier import SignatureVerifier

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Ingest"])


class TelemetryEventRequest(BaseModel):
    """Telemetry event in ingest request."""

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
    signature: str


class IngestRequest(BaseModel):
    """Telemetry batch ingest request."""

    batch_id: str
    device_id: str
    timestamp: int
    device_public_key: str
    batch_signature: str
    events: List[TelemetryEventRequest]


class IngestResponse(BaseModel):
    """Response for ingest request."""

    status: str
    batch_id: str
    events_ingested: int
    device_registered: bool


@router.post("/ingest/events", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_events(
    request: IngestRequest,
    db: Session = Depends(get_db)
) -> IngestResponse:
    """
    Ingest signed telemetry events from edge device.

    Steps:
    1. Verify batch signature with device public key
    2. Register device if unknown
    3. Verify individual event signatures
    4. Store events in database
    5. Update device last_seen timestamp

    Args:
        request: Telemetry batch ingest request
        db: Database session

    Returns:
        Ingest response with status and counts
    """
    try:
        # Verify batch signature
        batch_payload = {
            'batch_id': request.batch_id,
            'device_id': request.device_id,
            'timestamp': request.timestamp,
            'event_count': len(request.events),
            'event_ids': [e.event_id for e in request.events]
        }

        if not SignatureVerifier.verify_batch(
            request.device_public_key,
            batch_payload,
            request.batch_signature
        ):
            logger.warning(f"Invalid batch signature for device {request.device_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid batch signature"
            )

        # Register or retrieve device
        device = db.query(Device).filter(Device.device_id == request.device_id).first()
        device_registered = False

        if device is None:
            # Register new device
            device = Device(
                device_id=request.device_id,
                public_key=request.device_public_key,
                registered_at=datetime.utcnow(),
                last_seen=datetime.utcnow()
            )
            db.add(device)
            device_registered = True
            logger.info(f"Registered new device: {request.device_id}")
        else:
            # Verify public key matches (prevent key substitution)
            if device.public_key != request.device_public_key:
                logger.warning(f"Public key mismatch for device {request.device_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Device public key mismatch"
                )
            # Update last_seen
            device.last_seen = datetime.utcnow()

        # Verify and ingest events
        events_ingested = 0

        for event_req in request.events:
            # Verify event signature
            event_payload = {
                'event_id': event_req.event_id,
                'device_id': event_req.device_id,
                'timestamp': event_req.timestamp,
                'event_type': event_req.event_type,
                'outcome': event_req.outcome,
                'reason_codes': event_req.reason_codes,
            }

            if not SignatureVerifier.verify_event(
                request.device_public_key,
                event_payload,
                event_req.signature
            ):
                logger.warning(
                    f"Invalid event signature for event {event_req.event_id} "
                    f"from device {request.device_id}"
                )
                continue  # Skip invalid events, don't fail entire batch

            # Check if event already ingested
            existing = db.query(TelemetryEvent).filter(
                TelemetryEvent.event_id == event_req.event_id
            ).first()

            if existing:
                logger.debug(f"Event {event_req.event_id} already ingested, skipping")
                continue

            # Store event
            telemetry_event = TelemetryEvent(
                event_id=event_req.event_id,
                device_id=event_req.device_id,
                timestamp=event_req.timestamp,
                event_type=event_req.event_type,
                outcome=event_req.outcome,
                reason_codes=json.dumps(event_req.reason_codes),
                liveness_passed=event_req.liveness_passed,
                similarity_score=event_req.similarity_score,
                risk_score=event_req.risk_score,
                session_duration_seconds=event_req.session_duration_seconds,
                audit_event_hash=event_req.audit_event_hash,
                signature=event_req.signature,
            )
            db.add(telemetry_event)
            events_ingested += 1

        # Commit all changes
        db.commit()

        logger.info(
            f"Ingested {events_ingested}/{len(request.events)} events "
            f"from device {request.device_id}"
        )

        return IngestResponse(
            status="accepted",
            batch_id=request.batch_id,
            events_ingested=events_ingested,
            device_registered=device_registered
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ingest error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest telemetry"
        )
