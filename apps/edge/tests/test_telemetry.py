"""
Tests for sanitized telemetry events.
"""
import pytest
import time
from sentinelid_edge.services.telemetry.event import (
    TelemetryEvent, TelemetryBatch, TelemetryMapper
)
from sentinelid_edge.services.storage.repo_audit import AuditEvent
from sentinelid_edge.services.telemetry.signer import TelemetrySigner


class TestTelemetrySanitization:
    """Test that telemetry events are properly sanitized."""

    def test_telemetry_event_no_raw_data(self):
        """Test telemetry event contains no raw images or frames."""
        event = TelemetryEvent(
            event_id="test-1",
            device_id="device-1",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
            liveness_passed=True,
            signature="test_sig"
        )

        # Convert to dict
        event_dict = event.__dict__

        # Verify no raw data fields
        assert "frame" not in event_dict
        assert "image" not in event_dict
        assert "embedding" not in event_dict
        assert "landmarks" not in event_dict
        assert "face_metadata" not in event_dict

    def test_telemetry_mapper_sanitization(self):
        """Test mapping audit event to telemetry removes sensitive data."""
        audit_event = AuditEvent(
            event_id="audit-1",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
            liveness_passed=True,
            similarity_score=0.95,
        )

        telemetry = TelemetryMapper.from_audit_event(
            audit_event,
            device_id="device-1"
        )

        # Verify only sanitized fields present
        assert telemetry.outcome == "allow"
        assert telemetry.reason_codes == ["LIVENESS_PASSED"]
        assert telemetry.liveness_passed is True
        assert telemetry.similarity_score == 0.95

    def test_telemetry_to_dict_no_none_values(self):
        """Test telemetry dict removes None values."""
        event = TelemetryEvent(
            event_id="test-1",
            device_id="device-1",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["TEST"],
            liveness_passed=True,
            similarity_score=None,  # None value
        )

        event_dict = TelemetryMapper.to_dict(event)

        # None values should not be in dict
        assert "similarity_score" not in event_dict
        assert event_dict["outcome"] == "allow"

    def test_telemetry_batch_creation(self):
        """Test creating a telemetry batch."""
        event1 = TelemetryEvent(
            event_id="test-1",
            device_id="device-1",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
        )
        event2 = TelemetryEvent(
            event_id="test-2",
            device_id="device-1",
            timestamp=int(time.time()) + 1,
            event_type="auth_finished",
            outcome="deny",
            reason_codes=["LIVENESS_FAILED"],
        )

        batch = TelemetryBatch(
            batch_id="batch-1",
            device_id="device-1",
            timestamp=int(time.time()),
            events=[event1, event2]
        )

        assert len(batch.events) == 2
        assert batch.device_id == "device-1"

    def test_telemetry_contains_only_aggregates(self):
        """Test telemetry contains only aggregated data, no face info."""
        event = TelemetryEvent(
            event_id="test-1",
            device_id="device-1",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
            liveness_passed=True,
            similarity_score=0.95,  # Aggregated score
            risk_score=0.05,  # Aggregated score
            session_duration_seconds=30  # Aggregated duration
        )

        event_dict = TelemetryMapper.to_dict(event)

        # Only aggregated fields should be present
        assert "similarity_score" in event_dict
        assert "risk_score" in event_dict
        assert "session_duration_seconds" in event_dict
        assert event_dict["similarity_score"] == 0.95
        assert event_dict["risk_score"] == 0.05


class TestTelemetrySigning:
    """Test telemetry event signing."""

    def test_telemetry_signer_initialization(self, tmp_path):
        """Test initializing telemetry signer."""
        keychain_dir = str(tmp_path / "keys")
        signer = TelemetrySigner(keychain_dir)

        device_id = signer.get_device_id()
        assert device_id is not None
        assert len(device_id) > 0

    def test_telemetry_event_signing(self, tmp_path):
        """Test signing a telemetry event."""
        keychain_dir = str(tmp_path / "keys")
        signer = TelemetrySigner(keychain_dir)

        event = TelemetryEvent(
            event_id="test-1",
            device_id="device-1",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
        )

        signed_event = signer.sign_event(event)
        assert signed_event.signature is not None
        assert len(signed_event.signature) == 128  # ED25519 sig is 64 bytes = 128 hex chars

    def test_telemetry_batch_signing(self, tmp_path):
        """Test signing a telemetry batch."""
        keychain_dir = str(tmp_path / "keys")
        signer = TelemetrySigner(keychain_dir)

        event = TelemetryEvent(
            event_id="test-1",
            device_id="device-1",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
        )

        batch = TelemetryBatch(
            batch_id="batch-1",
            device_id="device-1",
            timestamp=int(time.time()),
            events=[event]
        )

        signed_batch = signer.sign_batch(batch)
        assert signed_batch.signature is not None
        assert len(signed_batch.signature) == 128  # ED25519 sig is 128 hex chars

    def test_signer_device_id_consistency(self, tmp_path):
        """Test device ID is consistent across signer instances."""
        keychain_dir = str(tmp_path / "keys")
        signer1 = TelemetrySigner(keychain_dir)
        device_id1 = signer1.get_device_id()

        signer2 = TelemetrySigner(keychain_dir)
        device_id2 = signer2.get_device_id()

        assert device_id1 == device_id2
