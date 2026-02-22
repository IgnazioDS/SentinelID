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
import json
import asyncio
import logging
from typing import List, Optional
from datetime import datetime
import httpx
from .event import TelemetryEvent, TelemetryBatch, TelemetryMapper
from .signer import TelemetrySigner
from ..storage.repo_outbox import OutboxRepository, OutboxEvent


logger = logging.getLogger(__name__)


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
        db_path: str = ".sentinelid/audit.db"
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
        self.last_export_attempt_time: Optional[datetime] = None
        self.last_export_error: Optional[str] = None

    def add_event(self, event: TelemetryEvent):
        """
        Add event to durable outbox.

        Args:
            event: Telemetry event to export
        """
        # Sign the event
        signed_event = self.signer.sign_event(event)

        # Create payload for single event
        payload = {
            'event': TelemetryMapper.to_dict(signed_event),
            'signature': signed_event.signature,
            'device_id': self.signer.get_device_id(),
            'device_public_key': self.signer.get_public_key(),
            'timestamp': int(datetime.utcnow().timestamp())
        }

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

        all_success = True

        # Try to export each event
        for event in events:
            success = await self._export_with_retry(event)

            if success:
                self.outbox.mark_sent(event.id)
            else:
                self.outbox.mark_failed_with_error(
                    event.id,
                    self.last_export_error or "Unknown error",
                    self.max_retries,
                    self.initial_backoff_seconds
                )
                all_success = False

        return all_success

    async def _export_with_retry(self, event: OutboxEvent) -> bool:
        """
        Export event with single attempt.

        Note: Retry backoff is managed by OutboxRepository; this method
        just attempts once and returns success/failure.

        Args:
            event: Outbox event to export

        Returns:
            True if export succeeded, False otherwise
        """
        try:
            success = await self._send_event(event)
            if success:
                self.last_export_attempt_time = datetime.utcnow()
                self.last_export_error = None
                return True
            else:
                self.last_export_attempt_time = datetime.utcnow()
                self.last_export_error = "HTTP error response"
                return False

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Telemetry export error: {error_msg}")
            self.last_export_attempt_time = datetime.utcnow()
            self.last_export_error = error_msg
            return False

    async def _send_event(self, event: OutboxEvent) -> bool:
        """
        Send individual event to cloud ingest endpoint.

        Args:
            event: Outbox event to send

        Returns:
            True if HTTP 2xx response, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.cloud_ingest_url,
                    json=event.payload,
                    headers={'Content-Type': 'application/json'}
                )

                success = response.status_code >= 200 and response.status_code < 300
                if not success:
                    logger.warning(
                        f"Telemetry export failed with status {response.status_code}: "
                        f"{response.text}"
                    )
                return success

        except Exception as e:
            logger.error(f"Failed to send telemetry event: {str(e)}")
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
            'last_export_attempt_time': self.last_export_attempt_time.isoformat() if self.last_export_attempt_time else None,
            'last_export_error': self.last_export_error
        }

    def replay_dlq_event(self, event_id: int):
        """
        Replay an event from DLQ back to PENDING.

        Args:
            event_id: ID of event in DLQ
        """
        self.outbox.replay_dlq_event(event_id)
        logger.info(f"Replayed DLQ event {event_id} back to PENDING")
