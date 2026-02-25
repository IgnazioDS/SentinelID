"""
Telemetry event ingest endpoint for edge devices.

Privacy enforcement:
  The ingest model is strict: it only accepts the fields defined below.
  Any attempt to submit raw frames, embeddings, landmarks, or face
  metadata will be rejected by Pydantic's model validator because those
  fields are not declared (extra = "forbid" on all models).
"""
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session
from datetime import datetime

# Use absolute imports for compatibility with uvicorn
import sys
import os
api_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(api_dir)
sys.path.insert(0, parent_dir)

from models import get_db, Device, TelemetryEvent
from api.signature_verifier import SignatureVerifier
from api.canonical import event_payload_for_signature, batch_payload_for_signature

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Ingest"])

# Fields that must never appear in telemetry
_FORBIDDEN_FIELDS = frozenset({
    "frame", "frames", "image", "embedding", "embeddings",
    "landmark", "landmarks", "face_data", "raw_face",
    "face_metadata", "face_image", "face_crop",
})


class TelemetryEventRequest(BaseModel):
    """
    Telemetry event in ingest request.

    Extra fields are forbidden: the model rejects any payload that
    includes frames, embeddings, landmarks, or raw face metadata.
    """
    model_config = ConfigDict(extra="forbid")

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

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        allowed = {"auth_started", "auth_finished", "enroll_started", "enroll_finished"}
        if v not in allowed:
            raise ValueError(f"event_type must be one of {sorted(allowed)}")
        return v

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v: str) -> str:
        allowed = {"allow", "deny", "error"}
        if v not in allowed:
            raise ValueError(f"outcome must be one of {sorted(allowed)}")
        return v


class IngestRequest(BaseModel):
    """
    Telemetry batch ingest request.

    Extra fields are forbidden at the batch level as well.
    """
    model_config = ConfigDict(extra="forbid")

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


def _event_as_payload(event: TelemetryEventRequest) -> Dict[str, Any]:
    """Return event payload as received over the wire (excluding Nones)."""
    return event.model_dump(exclude_none=True)


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
        # Enforce device_id invariant before any persistence.
        for event_req in request.events:
            if event_req.device_id != request.device_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "event.device_id must match batch.device_id "
                        f"(event_id={event_req.event_id})"
                    ),
                )

        # Verify batch signature over canonical full batch payload.
        events_payload = [_event_as_payload(event_req) for event_req in request.events]
        batch_payload = batch_payload_for_signature(
            batch_id=request.batch_id,
            device_id=request.device_id,
            timestamp=request.timestamp,
            events=events_payload,
        )

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

        # Verify every event signature before writing any records.
        for event_req in request.events:
            event_payload = event_payload_for_signature(_event_as_payload(event_req))

            if not SignatureVerifier.verify_event(
                request.device_public_key,
                event_payload,
                event_req.signature
            ):
                logger.warning(
                    f"Invalid event signature for event {event_req.event_id} "
                    f"from device {request.device_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid event signature for event_id={event_req.event_id}"
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

        events_ingested = 0
        for event_req in request.events:

            # Check if event already ingested
            existing = db.query(TelemetryEvent).filter(
                TelemetryEvent.event_id == event_req.event_id
            ).first()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Duplicate event_id {event_req.event_id}"
                )

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
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Ingest error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest telemetry"
        )
