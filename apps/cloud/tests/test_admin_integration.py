"""
Integration tests for admin dashboard API endpoints.
Tests the full flow from authentication to data retrieval.
"""
import io
import tarfile
import pytest
import os
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def admin_token():
    """Get the configured admin token."""
    return os.environ.get("ADMIN_API_TOKEN", "dev-admin-token")


@pytest.fixture
def client():
    """Create a test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(admin_token):
    """Create headers with admin token."""
    return {"X-Admin-Token": admin_token}


class TestAdminDevicesEndpoint:
    """Test /v1/admin/devices endpoint."""

    def test_devices_without_auth_returns_401(self, client):
        """Accessing devices without token returns 401."""
        response = client.get("/v1/admin/devices")
        assert response.status_code == 401

    def test_devices_with_invalid_token_returns_401(self, client):
        """Accessing devices with invalid token returns 401."""
        response = client.get(
            "/v1/admin/devices",
            headers={"X-Admin-Token": "invalid-token"}
        )
        assert response.status_code == 401

    def test_devices_with_valid_token_returns_200(self, client, auth_headers):
        """Accessing devices with valid token returns 200."""
        response = client.get("/v1/admin/devices", headers=auth_headers)
        assert response.status_code == 200

    def test_devices_returns_proper_structure(self, client, auth_headers):
        """Devices endpoint returns proper response structure."""
        response = client.get("/v1/admin/devices", headers=auth_headers)
        data = response.json()
        
        assert "devices" in data
        assert "total" in data
        assert isinstance(data["devices"], list)
        assert isinstance(data["total"], int)

    def test_devices_pagination_works(self, client, auth_headers):
        """Test pagination parameters."""
        response = client.get(
            "/v1/admin/devices?limit=10&offset=0",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["devices"]) <= 10


class TestAdminEventsEndpoint:
    """Test /v1/admin/events endpoint."""

    def test_events_without_auth_returns_401(self, client):
        """Accessing events without token returns 401."""
        response = client.get("/v1/admin/events")
        assert response.status_code == 401

    def test_events_with_valid_token_returns_200(self, client, auth_headers):
        """Accessing events with valid token returns 200."""
        response = client.get("/v1/admin/events", headers=auth_headers)
        assert response.status_code == 200

    def test_events_returns_proper_structure(self, client, auth_headers):
        """Events endpoint returns proper response structure."""
        response = client.get("/v1/admin/events", headers=auth_headers)
        data = response.json()
        
        assert "events" in data
        assert "total" in data
        assert isinstance(data["events"], list)
        assert isinstance(data["total"], int)

    def test_events_pagination_works(self, client, auth_headers):
        """Test pagination parameters."""
        response = client.get(
            "/v1/admin/events?limit=25&offset=0",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) <= 25

    def test_events_outcome_filter_works(self, client, auth_headers):
        """Test outcome filter parameter."""
        response = client.get(
            "/v1/admin/events?outcome=allow",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_events_request_and_session_filter_params_work(self, client, auth_headers):
        """Request/session correlation filters are accepted."""
        response = client.get(
            "/v1/admin/events?request_id=req-123&session_id=sess-123&reason_code=RISK_MEDIUM&start_ts=1&end_ts=9999999999&q=req-123",
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestAdminStatsEndpoint:
    """Test /v1/admin/stats endpoint."""

    def test_stats_without_auth_returns_401(self, client):
        """Accessing stats without token returns 401."""
        response = client.get("/v1/admin/stats")
        assert response.status_code == 401

    def test_stats_with_valid_token_returns_200(self, client, auth_headers):
        """Accessing stats with valid token returns 200."""
        response = client.get("/v1/admin/stats", headers=auth_headers)
        assert response.status_code == 200

    def test_stats_returns_all_metrics(self, client, auth_headers):
        """Stats endpoint returns all required metrics."""
        response = client.get("/v1/admin/stats", headers=auth_headers)
        data = response.json()
        
        numeric_fields = [
            "total_devices",
            "active_devices",
            "total_events",
            "allow_count",
            "deny_count",
            "error_count",
            "liveness_failure_rate",
            "ingest_success_count",
            "ingest_fail_count",
            "events_ingested_count",
            "ingest_window_seconds",
            "window_seconds",
            "window_events",
            "active_devices_window",
            "outbox_pending_total",
            "dlq_total",
        ]

        for field in numeric_fields:
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], (int, float))
        assert data["window"] in ("24h", "7d", "30d")
        assert isinstance(data["window_started_at"], str)

    def test_stats_liveness_failure_rate_is_percentage(self, client, auth_headers):
        """Liveness failure rate should be between 0 and 100."""
        response = client.get("/v1/admin/stats", headers=auth_headers)
        data = response.json()
        
        rate = data["liveness_failure_rate"]
        assert 0 <= rate <= 100, f"Invalid liveness rate: {rate}"
        assert isinstance(data["device_health"], list)

    def test_stats_range_filter_works(self, client, auth_headers):
        response = client.get("/v1/admin/stats?window=7d", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["window"] == "7d"


class TestAdminSeriesAndSupportEndpoints:
    def test_events_series_endpoint_returns_chart_shape(self, client, auth_headers):
        response = client.get("/v1/admin/events/series?window=24h", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "points" in body
        assert "outcome_breakdown" in body
        assert body["bucket"] in ("hour", "day")

    def test_device_detail_endpoint_handles_missing_device(self, client, auth_headers):
        response = client.get("/v1/admin/devices/does-not-exist", headers=auth_headers)
        assert response.status_code == 404

    def test_support_bundle_endpoint_returns_tarball(self, client, auth_headers):
        response = client.post("/v1/admin/support-bundle?window=24h&events_limit=25", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/gzip"
        assert "attachment;" in (response.headers.get("content-disposition") or "")
        assert response.headers.get("x-support-bundle-created-at")

        tar_bytes = io.BytesIO(response.content)
        with tarfile.open(fileobj=tar_bytes, mode="r:gz") as archive:
            names = set(archive.getnames())
            assert "stats.json" in names
            assert "events.json" in names
            assert "devices.json" in names
            assert "environment.json" in names
            events_raw = archive.extractfile("events.json")
            assert events_raw is not None
            payload = events_raw.read().decode("utf-8")
            assert "signature" not in payload.lower()
