from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from sentinelid_edge.main import app


def test_edge_response_includes_request_id_header() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    request_id = resp.headers.get("X-Request-Id")
    assert request_id is not None
    UUID(request_id)


def test_edge_propagates_incoming_request_id() -> None:
    client = TestClient(app)
    incoming = "req-custom-123"
    resp = client.get("/api/v1/health", headers={"X-Request-Id": incoming})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-Id") == incoming


def test_edge_generates_distinct_request_ids_per_request() -> None:
    client = TestClient(app)
    first = client.get("/api/v1/health")
    second = client.get("/api/v1/health")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers.get("X-Request-Id")
    assert second.headers.get("X-Request-Id")
    assert first.headers["X-Request-Id"] != second.headers["X-Request-Id"]
