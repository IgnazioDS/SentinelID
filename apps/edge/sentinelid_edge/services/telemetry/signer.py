"""Telemetry event signing with device keypair."""
from __future__ import annotations

from typing import Any, Dict, List

from .event import TelemetryEvent, TelemetryBatch, TelemetryMapper
from .canonical import canonical_json_bytes
from ..security.device_binding import DeviceBinding


class TelemetrySigner:
    """Signs telemetry events and batches with device private key."""

    def __init__(self, keychain_dir: str = ".sentinelid/keys"):
        """
        Initialize telemetry signer.

        Args:
            keychain_dir: Directory for key storage
        """
        self.device = DeviceBinding(keychain_dir)

    def sign_event(self, event: TelemetryEvent) -> TelemetryEvent:
        """
        Sign a telemetry event with device private key.

        Args:
            event: Telemetry event to sign

        Returns:
            Event with signature populated
        """
        payload = self.event_payload_for_signature(TelemetryMapper.to_dict(event))

        # Sign canonical JSON bytes shared with cloud verifier.
        signature = self.device.sign(canonical_json_bytes(payload))

        # Update event with signature
        event.signature = signature
        return event

    def sign_batch(self, batch: TelemetryBatch) -> TelemetryBatch:
        """
        Sign a telemetry batch with device private key.

        Args:
            batch: Telemetry batch to sign

        Returns:
            Batch with signature populated
        """
        events = [TelemetryMapper.to_dict(event) for event in batch.events]
        payload = self.batch_payload_for_signature(
            batch_id=batch.batch_id,
            device_id=batch.device_id,
            timestamp=batch.timestamp,
            events=events,
        )

        # Sign canonical JSON bytes shared with cloud verifier.
        signature = self.device.sign(canonical_json_bytes(payload))

        # Update batch with signature
        batch.signature = signature
        return batch

    def get_device_id(self) -> str:
        """Get the device ID."""
        return self.device.get_device_id()

    def get_public_key(self) -> str:
        """Get the device public key (for cloud registration)."""
        return self.device.get_public_key()

    def sign_batch_payload(self, payload: Dict[str, Any]) -> str:
        """Sign canonical batch payload bytes."""
        return self.device.sign(canonical_json_bytes(payload))

    @staticmethod
    def event_payload_for_signature(event_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return canonical signable event payload (exclude mutable signature field)."""
        payload = dict(event_payload)
        payload.pop("signature", None)
        return payload

    @staticmethod
    def batch_payload_for_signature(
        batch_id: str,
        device_id: str,
        timestamp: int,
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Return canonical signable batch payload.

        The batch signature covers full event objects exactly as transported
        (including each event signature) so cloud can verify a single canonical
        payload before persistence.
        """
        return {
            "batch_id": batch_id,
            "device_id": device_id,
            "timestamp": timestamp,
            "events": events,
        }
