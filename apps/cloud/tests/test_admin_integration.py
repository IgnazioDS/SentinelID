"""
Integration tests for admin dashboard API endpoints.
Tests the full flow from authentication to data retrieval.
"""
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
        
        required_fields = [
            "total_devices",
            "active_devices",
            "total_events",
            "allow_count",
            "deny_count",
            "error_count",
            "liveness_failure_rate"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], (int, float))

    def test_stats_liveness_failure_rate_is_percentage(self, client, auth_headers):
        """Liveness failure rate should be between 0 and 100."""
        response = client.get("/v1/admin/stats", headers=auth_headers)
        data = response.json()
        
        rate = data["liveness_failure_rate"]
        assert 0 <= rate <= 100, f"Invalid liveness rate: {rate}"
