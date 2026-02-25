"""End-to-end ingest tests for telemetry trust-chain and persistence."""
from __future__ import annotations

import tempfile
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from models import Device, SessionLocal, TelemetryEvent
from sentinelid_edge.services.telemetry.event import TelemetryBatch, TelemetryEvent as EdgeTelemetryEvent, TelemetryMapper
from sentinelid_edge.services.telemetry.signer import TelemetrySigner


@pytest.fixture(autouse=True)
def _reset_tables() -> None:
    db = SessionLocal()
    try:
        db.query(TelemetryEvent).delete()
        db.query(Device).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _build_signed_event(
    signer: TelemetrySigner,
    *,
    request_id: str | None = None,
    session_id: str | None = None,
) -> EdgeTelemetryEvent:
    event = EdgeTelemetryEvent(
        event_id=str(uuid.uuid4()),
        device_id=signer.get_device_id(),
        timestamp=int(time.time()),
        event_type="auth_finished",
        outcome="allow",
        reason_codes=["LIVENESS_PASSED"],
        liveness_passed=True,
        similarity_score=0.92,
        risk_score=0.07,
        session_duration_seconds=2,
        request_id=request_id,
        session_id=session_id,
        outbox_pending_count=3,
        dlq_count=1,
        last_error_summary="status=503",
    )
    signer.sign_event(event)
    return event


def test_ingest_e2e_persists_events(client: TestClient) -> None:
    with tempfile.TemporaryDirectory(prefix="sentinelid_ingest_e2e_") as keychain_dir:
        signer = TelemetrySigner(keychain_dir=keychain_dir)
        event = _build_signed_event(signer)

        batch = TelemetryBatch(
            batch_id=str(uuid.uuid4()),
            device_id=signer.get_device_id(),
            timestamp=int(time.time()),
            events=[event],
        )
        signer.sign_batch(batch)

        payload = {
            "batch_id": batch.batch_id,
            "device_id": batch.device_id,
            "timestamp": batch.timestamp,
            "device_public_key": signer.get_public_key(),
            "batch_signature": batch.signature,
            "events": [TelemetryMapper.to_dict(event)],
        }

        response = client.post("/v1/ingest/events", json=payload)
        assert response.status_code == 202, response.text
        data = response.json()
        assert data["status"] == "accepted"
        assert data["events_ingested"] == 1
        assert data["events_duplicated"] == 0
        assert data["events_received"] == 1

        db = SessionLocal()
        try:
            rows = db.query(TelemetryEvent).count()
            assert rows == 1
        finally:
            db.close()


def test_ingest_retry_is_idempotent_for_existing_event_id(client: TestClient) -> None:
    with tempfile.TemporaryDirectory(prefix="sentinelid_ingest_e2e_") as keychain_dir:
        signer = TelemetrySigner(keychain_dir=keychain_dir)
        event = _build_signed_event(signer)

        batch = TelemetryBatch(
            batch_id=str(uuid.uuid4()),
            device_id=signer.get_device_id(),
            timestamp=int(time.time()),
            events=[event],
        )
        signer.sign_batch(batch)

        payload = {
            "batch_id": batch.batch_id,
            "device_id": batch.device_id,
            "timestamp": batch.timestamp,
            "device_public_key": signer.get_public_key(),
            "batch_signature": batch.signature,
            "events": [TelemetryMapper.to_dict(event)],
        }

        first = client.post("/v1/ingest/events", json=payload)
        assert first.status_code == 202, first.text
        first_body = first.json()
        assert first_body["events_ingested"] == 1
        assert first_body["events_duplicated"] == 0

        second = client.post("/v1/ingest/events", json=payload)
        assert second.status_code == 202, second.text
        second_body = second.json()
        assert second_body["events_ingested"] == 0
        assert second_body["events_duplicated"] == 1
        assert second_body["events_received"] == 1

        db = SessionLocal()
        try:
            rows = db.query(TelemetryEvent).count()
            assert rows == 1
        finally:
            db.close()


def test_ingest_persists_and_filters_request_and_session_ids(client: TestClient) -> None:
    with tempfile.TemporaryDirectory(prefix="sentinelid_ingest_e2e_") as keychain_dir:
        signer = TelemetrySigner(keychain_dir=keychain_dir)
        req_id = "req-e2e-001"
        sess_id = "sess-e2e-001"
        event = _build_signed_event(signer, request_id=req_id, session_id=sess_id)

        batch = TelemetryBatch(
            batch_id=str(uuid.uuid4()),
            device_id=signer.get_device_id(),
            timestamp=int(time.time()),
            events=[event],
        )
        signer.sign_batch(batch)

        payload = {
            "batch_id": batch.batch_id,
            "device_id": batch.device_id,
            "timestamp": batch.timestamp,
            "device_public_key": signer.get_public_key(),
            "batch_signature": batch.signature,
            "events": [TelemetryMapper.to_dict(event)],
        }

        ingest = client.post("/v1/ingest/events", json=payload)
        assert ingest.status_code == 202, ingest.text

        db = SessionLocal()
        try:
            row = db.query(TelemetryEvent).first()
            assert row is not None
            assert row.request_id == req_id
            assert row.session_id == sess_id
            assert row.outbox_pending_count == 3
            assert row.dlq_count == 1
            assert row.last_error_summary == "status=503"
        finally:
            db.close()

        headers = {"X-Admin-Token": "dev-admin-token"}
        by_request = client.get(f"/v1/admin/events?request_id={req_id}", headers=headers)
        assert by_request.status_code == 200, by_request.text
        request_events = by_request.json()["events"]
        assert len(request_events) == 1
        assert request_events[0]["request_id"] == req_id

        by_session = client.get(f"/v1/admin/events?session_id={sess_id}", headers=headers)
        assert by_session.status_code == 200, by_session.text
        session_events = by_session.json()["events"]
        assert len(session_events) == 1
        assert session_events[0]["session_id"] == sess_id


def test_ingest_rejects_duplicate_event_ids_inside_same_batch(client: TestClient) -> None:
    with tempfile.TemporaryDirectory(prefix="sentinelid_ingest_e2e_") as keychain_dir:
        signer = TelemetrySigner(keychain_dir=keychain_dir)
        event = _build_signed_event(signer)
        event_payload = TelemetryMapper.to_dict(event)

        batch_id = str(uuid.uuid4())
        ts = int(time.time())
        signable_batch_payload = signer.batch_payload_for_signature(
            batch_id=batch_id,
            device_id=signer.get_device_id(),
            timestamp=ts,
            events=[event_payload, event_payload],
        )

        payload = {
            "batch_id": batch_id,
            "device_id": signer.get_device_id(),
            "timestamp": ts,
            "device_public_key": signer.get_public_key(),
            "batch_signature": signer.sign_batch_payload(signable_batch_payload),
            "events": [event_payload, event_payload],
        }

        response = client.post("/v1/ingest/events", json=payload)
        assert response.status_code == 409, response.text

        db = SessionLocal()
        try:
            rows = db.query(TelemetryEvent).count()
            assert rows == 0
        finally:
            db.close()


def test_ingest_rejects_tampered_event_signature_and_persists_zero(client: TestClient) -> None:
    with tempfile.TemporaryDirectory(prefix="sentinelid_ingest_e2e_") as keychain_dir:
        signer = TelemetrySigner(keychain_dir=keychain_dir)
        event = _build_signed_event(signer)
        tampered_event = TelemetryMapper.to_dict(event)
        tampered_event["outcome"] = "deny"

        batch_id = str(uuid.uuid4())
        ts = int(time.time())
        signable_batch_payload = signer.batch_payload_for_signature(
            batch_id=batch_id,
            device_id=signer.get_device_id(),
            timestamp=ts,
            events=[tampered_event],
        )

        payload = {
            "batch_id": batch_id,
            "device_id": signer.get_device_id(),
            "timestamp": ts,
            "device_public_key": signer.get_public_key(),
            "batch_signature": signer.sign_batch_payload(signable_batch_payload),
            "events": [tampered_event],
        }

        response = client.post("/v1/ingest/events", json=payload)
        assert response.status_code == 401, response.text

        db = SessionLocal()
        try:
            rows = db.query(TelemetryEvent).count()
            assert rows == 0
        finally:
            db.close()


def test_ingest_rejects_device_id_mismatch_and_persists_zero(client: TestClient) -> None:
    with tempfile.TemporaryDirectory(prefix="sentinelid_ingest_e2e_") as keychain_dir:
        signer = TelemetrySigner(keychain_dir=keychain_dir)
        event = _build_signed_event(signer)
        mismatched = TelemetryMapper.to_dict(event)
        mismatched["device_id"] = "different-device-id"

        batch_id = str(uuid.uuid4())
        ts = int(time.time())
        signable_batch_payload = signer.batch_payload_for_signature(
            batch_id=batch_id,
            device_id=signer.get_device_id(),
            timestamp=ts,
            events=[mismatched],
        )

        payload = {
            "batch_id": batch_id,
            "device_id": signer.get_device_id(),
            "timestamp": ts,
            "device_public_key": signer.get_public_key(),
            "batch_signature": signer.sign_batch_payload(signable_batch_payload),
            "events": [mismatched],
        }

        response = client.post("/v1/ingest/events", json=payload)
        assert response.status_code == 422, response.text

        db = SessionLocal()
        try:
            rows = db.query(TelemetryEvent).count()
            assert rows == 0
        finally:
            db.close()
