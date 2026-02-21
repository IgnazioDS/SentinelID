"""
Telemetry event signing with device keypair.
"""
import json
from typing import List
from .event import TelemetryEvent, TelemetryBatch, TelemetryMapper
from ..security.device_binding import DeviceBinding
from ..security.crypto import CryptoProvider


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
        # Create payload without signature
        payload = TelemetryMapper.to_dict(event)
        if 'signature' in payload:
            del payload['signature']

        # Sign the canonical JSON
        payload_json = json.dumps(payload, sort_keys=True)
        signature = self.device.sign(payload_json.encode())

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
        # Create payload without signature
        payload = {
            'batch_id': batch.batch_id,
            'device_id': batch.device_id,
            'timestamp': batch.timestamp,
            'event_count': len(batch.events),
            'event_ids': [e.event_id for e in batch.events]
        }

        # Sign the canonical JSON
        payload_json = json.dumps(payload, sort_keys=True)
        signature = self.device.sign(payload_json.encode())

        # Update batch with signature
        batch.signature = signature
        return batch

    def get_device_id(self) -> str:
        """Get the device ID."""
        return self.device.get_device_id()

    def get_public_key(self) -> str:
        """Get the device public key (for cloud registration)."""
        return self.device.get_public_key()
