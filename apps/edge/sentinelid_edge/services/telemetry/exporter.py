"""
Telemetry event exporter with durable outbox pattern.

Features:
- Durable event storage in SQLite outbox
- Batch event collection
- Exponential backoff with jitter on failures
- Automatic retry with configurable limits
- Dead Letter Queue (DLQ) for undeliverable events
- Restart-safe: resumes from outbox on startup
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import httpx
from .event import TelemetryEvent, TelemetryMapper
from .signer import TelemetrySigner
from ..storage.repo_outbox import OutboxRepository, OutboxEvent


logger = logging.getLogger(__name__)


def _sanitize_error_text(value: str) -> str:
    """Compact exception text for durable outbox metadata."""
    return " ".join(str(value).split())[:240]


class TelemetryExporter:
    """
    Exports signed telemetry events to cloud ingest endpoint with durability.

    Uses outbox pattern to guarantee no event loss across restarts.
    Implements exponential backoff with jitter for failed events.
    Moves undeliverable events to DLQ after max attempts.
    """

    def __init__(
        self,
        cloud_ingest_url: str,
        batch_size: int = 10,
        max_retries: int = 5,
        initial_backoff_seconds: float = 1.0,
        keychain_dir: str = ".sentinelid/keys",
        db_path: str = ".sentinelid/audit.db",
        http_timeout_seconds: float = 10.0,
    ):
        """
        Initialize telemetry exporter.

        Args:
            cloud_ingest_url: Cloud ingest endpoint URL
            batch_size: Number of events to batch before export
            max_retries: Maximum number of retry attempts
            initial_backoff_seconds: Initial backoff for exponential retry
            keychain_dir: Directory for key storage
            db_path: Path to SQLite database
        """
        self.cloud_ingest_url = cloud_ingest_url
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds
        self.signer = TelemetrySigner(keychain_dir)
        self.outbox = OutboxRepository(db_path)
        self.http_timeout_seconds = max(1.0, float(http_timeout_seconds))
        self.last_export_attempt_time: Optional[datetime] = None
        self.last_export_success_time: Optional[datetime] = None
        self.last_export_error: Optional[str] = None

    def add_event(self, event: TelemetryEvent):
        """
        Add event to durable outbox.

        Args:
            event: Telemetry event to export
        """
        # Enforce exporter/device identity consistency.
        device_id = self.signer.get_device_id()
        if event.device_id != device_id:
            logger.warning(
                "Telemetry event device_id mismatch detected; normalizing event_id=%s",
                event.event_id,
            )
            event.device_id = device_id

        # Sign the event
        signed_event = self.signer.sign_event(event)
        payload = TelemetryMapper.to_dict(signed_event)

        # Store in durable outbox
        self.outbox.add_event(payload)

    async def export_pending(self, force: bool = False) -> bool:
        """
        Export pending events from outbox.

        Args:
            force: Force export even if batch not full

        Returns:
            True if all events processed, False if errors occurred
        """
        # Get pending events due for delivery
        pending = self.outbox.get_pending_events(limit=self.batch_size)

        if len(pending) == 0:
            return True

        if len(pending) < self.batch_size and not force:
            # Not enough events to batch yet
            return True

        # Export this batch
        success = await self._export_batch(pending)

        if success:
            logger.info(f"Exported telemetry batch with {len(pending)} events from outbox")

        return success

    async def _export_batch(self, events: List[OutboxEvent]) -> bool:
        """
        Export a batch of events from the outbox.

        Args:
            events: List of outbox events to export

        Returns:
            True if all events exported successfully
        """
        if not events:
            return True

        batch_payload = self._build_ingest_batch(events)
        if batch_payload is None:
            for outbox_event in events:
                self.outbox.mark_failed_with_error(
                    outbox_event.id,
                    self.last_export_error or "Invalid outbox payload",
                    self.max_retries,
                    self.initial_backoff_seconds,
                )
            return False

        success = await self._send_batch(batch_payload)
        if success:
            self.last_export_attempt_time = datetime.now(timezone.utc)
            self.last_export_success_time = self.last_export_attempt_time
            self.last_export_error = None
            for outbox_event in events:
                self.outbox.mark_sent(outbox_event.id)
            return True

        self.last_export_attempt_time = datetime.now(timezone.utc)
        for outbox_event in events:
            self.outbox.mark_failed_with_error(
                outbox_event.id,
                self.last_export_error or "HTTP error response",
                self.max_retries,
                self.initial_backoff_seconds,
            )
        return False

    def _extract_event_payload(self, outbox_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract event payload from outbox row.

        Supports legacy rows stored as {"event": {...}} and current rows
        stored directly as event payload objects.
        """
        if isinstance(outbox_payload.get("event"), dict):
            payload = dict(outbox_payload["event"])
        else:
            payload = dict(outbox_payload)
        if "event_id" not in payload or "signature" not in payload:
            return None
        return payload

    def _build_ingest_batch(self, events: List[OutboxEvent]) -> Optional[Dict[str, Any]]:
        """Build canonical cloud ingest batch from pending outbox rows."""
        device_id = self.signer.get_device_id()
        event_payloads: List[Dict[str, Any]] = []
        for outbox_event in events:
            payload = self._extract_event_payload(outbox_event.payload)
            if payload is None:
                self.last_export_error = f"Invalid outbox payload for id={outbox_event.id}"
                return None
            if payload.get("device_id") != device_id:
                self.last_export_error = (
                    f"event.device_id mismatch for event_id={payload.get('event_id')}"
                )
                return None
            event_payloads.append(payload)

        timestamp = int(datetime.now(timezone.utc).timestamp())
        batch_id = str(uuid4())
        batch_signable_payload = self.signer.batch_payload_for_signature(
            batch_id=batch_id,
            device_id=device_id,
            timestamp=timestamp,
            events=event_payloads,
        )
        batch_signature = self.signer.sign_batch_payload(batch_signable_payload)
        return {
            "batch_id": batch_id,
            "device_id": device_id,
            "timestamp": timestamp,
            "device_public_key": self.signer.get_public_key(),
            "batch_signature": batch_signature,
            "events": event_payloads,
        }

    async def _send_batch(self, payload: Dict[str, Any]) -> bool:
        """Send one telemetry batch to cloud ingest endpoint."""
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout_seconds) as client:
                response = await client.post(
                    self.cloud_ingest_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                success = response.status_code >= 200 and response.status_code < 300
                if not success:
                    logger.warning(
                        "Telemetry export failed with status %s: %s",
                        response.status_code,
                        response.text,
                    )
                    self.last_export_error = _sanitize_error_text(f"status={response.status_code}")
                    return False

                data = response.json() if response.content else {}
                ingested = int(data.get("events_ingested", 0))
                duplicated = int(data.get("events_duplicated", 0))
                expected = len(payload["events"])
                if (ingested + duplicated) != expected:
                    logger.warning(
                        (
                            "Telemetry batch ingest mismatch events_ingested=%s "
                            "events_duplicated=%s expected=%s body=%s"
                        ),
                        ingested,
                        duplicated,
                        expected,
                        data,
                    )
                    self.last_export_error = _sanitize_error_text(
                        "events_ingested_mismatch "
                        f"ingested={ingested} duplicated={duplicated} expected={expected}"
                    )
                    return False
                return success

        except Exception as e:
            logger.error(f"Failed to send telemetry event: {str(e)}")
            self.last_export_error = _sanitize_error_text(str(e))
            return False

    async def flush(self) -> bool:
        """
        Force export of all pending events.

        Returns:
            True if all events exported, False otherwise
        """
        return await self.export_pending(force=True)

    def get_stats(self) -> dict:
        """
        Get exporter statistics.

        Returns:
            Dictionary with pending_count, dlq_count, sent_count, and last attempt info
        """
        outbox_stats = self.outbox.get_stats()
        return {
            **outbox_stats,
            "last_export_attempt_time": (
                self.last_export_attempt_time.isoformat()
                if self.last_export_attempt_time
                else outbox_stats.get("last_attempt_at")
            ),
            "last_export_success_time": (
                self.last_export_success_time.isoformat()
                if self.last_export_success_time
                else outbox_stats.get("last_success_at")
            ),
            "last_export_error": self.last_export_error or outbox_stats.get("last_error_summary"),
        }

    def replay_dlq_event(self, event_id: int):
        """
        Replay an event from DLQ back to PENDING.

        Args:
            event_id: ID of event in DLQ
        """
        self.outbox.replay_dlq_event(event_id)
        logger.info(f"Replayed DLQ event {event_id} back to PENDING")

    def replay_dlq_events(self, limit: int = 100) -> int:
        """Replay up to limit DLQ events back to PENDING."""
        replayed = self.outbox.replay_dlq_events(limit=limit)
        logger.info("Replayed %s DLQ events back to PENDING", replayed)
        return replayed
