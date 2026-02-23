"""
Tests that telemetry ingest model rejects forbidden fields.

Forbidden fields are those that would constitute privacy violations:
raw frames, face embeddings, landmarks, and raw face metadata.
This test MUST FAIL if any of those fields are accepted by the model.
"""
import json
import os
import sys

import pytest
from pydantic import ValidationError

# conftest.py stubs psycopg2 and models so this import works without PostgreSQL
from api.ingest_router import IngestRequest, TelemetryEventRequest, _FORBIDDEN_FIELDS

VALID_EVENT = {
    "event_id": "evt-001",
    "device_id": "dev-001",
    "timestamp": 1700000000,
    "event_type": "auth_finished",
    "outcome": "allow",
    "reason_codes": ["liveness_ok"],
    "liveness_passed": True,
    "similarity_score": 0.95,
    "risk_score": 0.02,
    "session_duration_seconds": 5,
    "audit_event_hash": "abc123",
    "signature": "deadbeef",
}

VALID_BATCH = {
    "batch_id": "batch-001",
    "device_id": "dev-001",
    "timestamp": 1700000000,
    "device_public_key": "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
    "batch_signature": "deadbeef",
    "events": [VALID_EVENT],
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _event_with_extra(**extra):
    """Return a copy of VALID_EVENT with extra fields added."""
    return {**VALID_EVENT, **extra}


def _batch_with_extra_event(**extra):
    """Return a batch whose single event has the given extra fields."""
    return {**VALID_BATCH, "events": [_event_with_extra(**extra)]}


def _batch_with_extra(**extra):
    """Return a batch with the given extra fields at the batch level."""
    return {**VALID_BATCH, **extra}


# ---------------------------------------------------------------------------
# Test: valid payload is accepted
# ---------------------------------------------------------------------------

class TestValidPayload:
    def test_valid_event_accepted(self):
        event = TelemetryEventRequest(**VALID_EVENT)
        assert event.event_id == "evt-001"

    def test_valid_batch_accepted(self):
        batch = IngestRequest(**VALID_BATCH)
        assert batch.batch_id == "batch-001"
        assert len(batch.events) == 1

    def test_valid_outcomes(self):
        for outcome in ("allow", "deny", "error"):
            e = TelemetryEventRequest(**{**VALID_EVENT, "outcome": outcome})
            assert e.outcome == outcome

    def test_valid_event_types(self):
        for et in ("auth_started", "auth_finished", "enroll_started", "enroll_finished"):
            e = TelemetryEventRequest(**{**VALID_EVENT, "event_type": et})
            assert e.event_type == et


# ---------------------------------------------------------------------------
# Test: forbidden fields at event level are rejected
# ---------------------------------------------------------------------------

class TestForbiddenEventFields:
    @pytest.mark.parametrize("field_name", [
        "frame",
        "frames",
        "image",
        "embedding",
        "embeddings",
        "landmark",
        "landmarks",
        "face_data",
        "raw_face",
        "face_metadata",
        "face_image",
        "face_crop",
    ])
    def test_forbidden_field_rejected(self, field_name):
        """Submitting a forbidden field MUST raise ValidationError."""
        payload = _event_with_extra(**{field_name: "sensitive-data"})
        with pytest.raises(ValidationError) as exc_info:
            TelemetryEventRequest(**payload)
        # Confirm extra-fields error (not a different validation issue)
        errors = exc_info.value.errors()
        assert any("extra" in str(e).lower() or field_name in str(e) for e in errors), \
            f"Expected extra-field rejection for {field_name!r}, got: {errors}"

    def test_forbidden_field_names_constant_is_complete(self):
        """Ensure _FORBIDDEN_FIELDS covers the minimum expected set."""
        required = {
            "frame", "frames", "image", "embedding", "embeddings",
            "landmark", "landmarks", "face_data", "raw_face", "face_metadata",
        }
        missing = required - _FORBIDDEN_FIELDS
        assert not missing, f"_FORBIDDEN_FIELDS is missing: {missing}"


# ---------------------------------------------------------------------------
# Test: forbidden fields at batch level are rejected
# ---------------------------------------------------------------------------

class TestForbiddenBatchFields:
    @pytest.mark.parametrize("field_name", [
        "frame", "embedding", "landmarks", "raw_face",
    ])
    def test_forbidden_field_at_batch_level_rejected(self, field_name):
        payload = _batch_with_extra(**{field_name: "sensitive-data"})
        with pytest.raises(ValidationError):
            IngestRequest(**payload)


# ---------------------------------------------------------------------------
# Test: invalid field values are rejected
# ---------------------------------------------------------------------------

class TestFieldValidation:
    def test_invalid_outcome_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryEventRequest(**{**VALID_EVENT, "outcome": "unknown"})

    def test_invalid_event_type_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryEventRequest(**{**VALID_EVENT, "event_type": "raw_capture"})

    def test_arbitrary_extra_field_at_batch_level(self):
        with pytest.raises(ValidationError):
            IngestRequest(**_batch_with_extra(surprise="unexpected"))

    def test_arbitrary_extra_field_at_event_level(self):
        with pytest.raises(ValidationError):
            TelemetryEventRequest(**_event_with_extra(surprise="unexpected"))
