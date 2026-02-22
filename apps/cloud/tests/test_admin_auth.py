"""
Tests for admin authentication.
"""
import pytest
import os
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from main import app
    return TestClient(app)


def test_admin_events_missing_token(client):
    """Test that /v1/admin/events rejects requests without token."""
    response = client.get("/v1/admin/events")
    assert response.status_code == 401
    assert "Missing X-Admin-Token" in response.json()["detail"]


def test_admin_events_invalid_token(client):
    """Test that /v1/admin/events rejects requests with wrong token."""
    response = client.get(
        "/v1/admin/events",
        headers={"X-Admin-Token": "wrong-token"}
    )
    assert response.status_code == 401
    assert "Invalid admin token" in response.json()["detail"]


def test_admin_events_valid_token(client):
    """Test that /v1/admin/events accepts valid token."""
    # Use default dev token
    response = client.get(
        "/v1/admin/events",
        headers={"X-Admin-Token": "dev-admin-token"}
    )
    # Will fail due to no database, but should pass auth
    assert response.status_code in [200, 422, 500]  # Auth passed, may fail on DB


def test_admin_stats_requires_auth(client):
    """Test that /v1/admin/stats requires authentication."""
    response = client.get("/v1/admin/stats")
    assert response.status_code == 401


def test_admin_devices_requires_auth(client):
    """Test that /v1/admin/devices requires authentication."""
    response = client.get("/v1/admin/devices")
    assert response.status_code == 401


def test_admin_devices_valid_token(client):
    """Test that /v1/admin/devices accepts valid token."""
    response = client.get(
        "/v1/admin/devices",
        headers={"X-Admin-Token": "dev-admin-token"}
    )
    # Auth should pass
    assert response.status_code in [200, 422, 500]


def test_token_from_environment():
    """Test that token can be set from environment variable."""
    # Save original
    original_token = os.environ.get("ADMIN_API_TOKEN")

    try:
        # Set custom token
        os.environ["ADMIN_API_TOKEN"] = "custom-secret-token"

        from main import app
        client = TestClient(app)

        # Should reject old token
        response = client.get(
            "/v1/admin/events",
            headers={"X-Admin-Token": "dev-admin-token"}
        )
        assert response.status_code == 401

        # Should accept new token
        response = client.get(
            "/v1/admin/events",
            headers={"X-Admin-Token": "custom-secret-token"}
        )
        assert response.status_code in [200, 422, 500]  # Auth passed

    finally:
        # Restore original
        if original_token:
            os.environ["ADMIN_API_TOKEN"] = original_token
        elif "ADMIN_API_TOKEN" in os.environ:
            del os.environ["ADMIN_API_TOKEN"]
