"""
Telemetry event exporter with retry and backoff.
"""
import json
import asyncio
import logging
from typing import List, Optional
from datetime import datetime
import httpx
from .event import TelemetryEvent, TelemetryBatch, TelemetryMapper
from .signer import TelemetrySigner


logger = logging.getLogger(__name__)


class TelemetryExporter:
    """
    Exports signed telemetry events to cloud ingest endpoint.

    Features:
    - Batch event collection
    - Exponential backoff on failures
    - Automatic retry with configurable limits
    """

    def __init__(
        self,
        cloud_ingest_url: str,
        batch_size: int = 10,
        max_retries: int = 3,
        initial_backoff_seconds: float = 1.0,
        keychain_dir: str = ".sentinelid/keys"
    ):
        """
        Initialize telemetry exporter.

        Args:
            cloud_ingest_url: Cloud ingest endpoint URL
            batch_size: Number of events to batch before export
            max_retries: Maximum number of retry attempts
            initial_backoff_seconds: Initial backoff for exponential retry
            keychain_dir: Directory for key storage
        """
        self.cloud_ingest_url = cloud_ingest_url
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds
        self.signer = TelemetrySigner(keychain_dir)
        self.pending_events: List[TelemetryEvent] = []

    def add_event(self, event: TelemetryEvent):
        """
        Add event to pending batch.

        Args:
            event: Telemetry event to export
        """
        # Sign the event
        signed_event = self.signer.sign_event(event)
        self.pending_events.append(signed_event)

    async def export_batch(self, force: bool = False) -> bool:
        """
        Export pending batch if full or forced.

        Args:
            force: Force export even if batch not full

        Returns:
            True if export succeeded, False otherwise
        """
        if len(self.pending_events) == 0:
            return True

        if len(self.pending_events) < self.batch_size and not force:
            return True

        # Create batch
        batch = TelemetryBatch(
            batch_id=str(asyncio.current_task().get_name() if asyncio.current_task() else ""),
            device_id=self.signer.get_device_id(),
            timestamp=int(datetime.utcnow().timestamp()),
            events=self.pending_events.copy()
        )

        # Sign batch
        signed_batch = self.signer.sign_batch(batch)

        # Export with retry
        success = await self._export_with_retry(signed_batch)

        if success:
            self.pending_events.clear()
            logger.info(f"Exported telemetry batch with {len(batch.events)} events")

        return success

    async def _export_with_retry(self, batch: TelemetryBatch) -> bool:
        """
        Export batch with exponential backoff retry.

        Args:
            batch: Signed telemetry batch

        Returns:
            True if export succeeded, False otherwise
        """
        backoff = self.initial_backoff_seconds

        for attempt in range(self.max_retries + 1):
            try:
                success = await self._send_batch(batch)
                if success:
                    return True

                if attempt < self.max_retries:
                    logger.warning(
                        f"Telemetry export failed (attempt {attempt + 1}), "
                        f"retrying in {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2  # Exponential backoff

            except Exception as e:
                logger.error(f"Telemetry export error: {str(e)}")
                if attempt < self.max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2

        logger.error(f"Telemetry export failed after {self.max_retries + 1} attempts")
        return False

    async def _send_batch(self, batch: TelemetryBatch) -> bool:
        """
        Send batch to cloud ingest endpoint.

        Args:
            batch: Signed telemetry batch

        Returns:
            True if HTTP 202+ response, False otherwise
        """
        try:
            payload = {
                'batch_id': batch.batch_id,
                'device_id': batch.device_id,
                'timestamp': batch.timestamp,
                'device_public_key': self.signer.get_public_key(),
                'batch_signature': batch.signature,
                'events': [
                    {
                        **TelemetryMapper.to_dict(event),
                        'signature': event.signature
                    }
                    for event in batch.events
                ]
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.cloud_ingest_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                )

                return response.status_code >= 200 and response.status_code < 300

        except Exception as e:
            logger.error(f"Failed to send telemetry batch: {str(e)}")
            return False

    async def flush(self) -> bool:
        """
        Force export of all pending events.

        Returns:
            True if export succeeded, False otherwise
        """
        return await self.export_batch(force=True)
