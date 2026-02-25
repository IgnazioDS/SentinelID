"""
Telemetry event model (sanitized, no images/embeddings/PII).
"""
from typing import Any, Optional, List
from dataclasses import dataclass, asdict
from ..storage.repo_audit import AuditEvent


@dataclass
class TelemetryEvent:
    """
    Sanitized telemetry event for cloud reporting.

    Contains NO:
    - Raw images or frames
    - Face embeddings
    - Face metadata (landmarks, bounding boxes)
    - Personally identifiable information
    - Session frame data

    Contains ONLY:
    - Decision outcome and reason codes
    - Aggregated scores (liveness, risk, similarity)
    - Audit event hash (for cloud-side linkage)
    - Device and session identifiers
    """

    event_id: str
    device_id: str
    timestamp: int
    event_type: str  # "auth_started", "auth_finished"
    outcome: str  # "allow", "deny", "error"
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
    signature: Optional[str] = None  # Populated by signer


@dataclass
class TelemetryBatch:
    """Batch of telemetry events for export."""

    batch_id: str
    device_id: str
    timestamp: int
    events: List[TelemetryEvent]
    signature: Optional[str] = None  # Signature of entire batch


class TelemetryMapper:
    """Maps audit events to sanitized telemetry events."""

    @staticmethod
    def from_audit_event(
        audit_event: AuditEvent,
        device_id: str,
        session_start_time: Optional[int] = None,
        exporter_snapshot: Optional[dict[str, Any]] = None,
    ) -> TelemetryEvent:
        """
        Convert audit event to sanitized telemetry event.

        Args:
            audit_event: Source audit event
            device_id: Device identifier
            session_start_time: Optional session start timestamp for duration

        Returns:
            Sanitized telemetry event
        """
        session_duration = None
        if session_start_time and audit_event.timestamp:
            session_duration = max(0, int(audit_event.timestamp - int(session_start_time)))

        return TelemetryEvent(
            event_id=audit_event.event_id,
            device_id=device_id,
            timestamp=audit_event.timestamp,
            event_type=audit_event.event_type,
            outcome=audit_event.outcome,
            reason_codes=audit_event.reason_codes,
            liveness_passed=audit_event.liveness_passed,
            similarity_score=audit_event.similarity_score,
            risk_score=audit_event.risk_score,
            session_duration_seconds=session_duration,
            session_id=audit_event.session_id,
            request_id=audit_event.request_id,
            outbox_pending_count=(
                int(exporter_snapshot["pending_count"])
                if exporter_snapshot and exporter_snapshot.get("pending_count") is not None
                else None
            ),
            dlq_count=(
                int(exporter_snapshot["dlq_count"])
                if exporter_snapshot and exporter_snapshot.get("dlq_count") is not None
                else None
            ),
            last_error_summary=(
                str(exporter_snapshot.get("last_error_summary"))
                if exporter_snapshot and exporter_snapshot.get("last_error_summary")
                else None
            ),
            audit_event_hash=audit_event.hash,
        )

    @staticmethod
    def to_dict(event: TelemetryEvent) -> dict:
        """
        Convert telemetry event to dictionary (for JSON serialization).

        Args:
            event: Telemetry event

        Returns:
            Dictionary representation
        """
        data = asdict(event)
        # Remove None values to keep payload clean
        return {k: v for k, v in data.items() if v is not None}
