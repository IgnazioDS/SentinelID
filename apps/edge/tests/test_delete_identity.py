"""
Tests for the /v1/settings/delete_identity endpoint.
"""
import json
import os
import secrets
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sentinelid_edge.services.security.encryption import _KEY_BYTES


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset module-level singletons between tests."""
    import sentinelid_edge.services.security.encryption as enc
    import sentinelid_edge.services.storage.db as db_mod
    old_enc = enc._provider
    old_db = db_mod._db_instance
    enc._provider = None
    db_mod._db_instance = None
    yield
    enc._provider = old_enc
    db_mod._db_instance = old_db


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """Set up isolated DB + keys environment."""
    db_path = str(tmp_path / "test.db")
    key_dir = str(tmp_path / "keys")
    master_key = secrets.token_bytes(_KEY_BYTES)

    monkeypatch.setenv("SENTINELID_MASTER_KEY", master_key.hex())
    monkeypatch.setenv("SENTINELID_DB_PATH", db_path)
    monkeypatch.setenv("SENTINELID_KEYCHAIN_DIR", key_dir)

    # Re-import settings after env change
    import importlib
    import sentinelid_edge.core.config as cfg_mod
    importlib.reload(cfg_mod)

    yield db_path, key_dir, master_key


@pytest.fixture
def client(tmp_env, monkeypatch):
    """Create TestClient with isolated settings."""
    db_path, key_dir, _ = tmp_env
    # Patch settings before importing app
    import sentinelid_edge.core.config as cfg_mod
    import sentinelid_edge.core.auth as auth_mod
    cfg_mod.settings.DB_PATH = db_path
    cfg_mod.settings.KEYCHAIN_DIR = key_dir
    cfg_mod.settings.EDGE_AUTH_TOKEN = "testtoken"
    auth_mod.settings = cfg_mod.settings

    import importlib
    import sentinelid_edge.main as main_mod
    importlib.reload(main_mod)
    return TestClient(
        main_mod.app,
        headers={"Authorization": f"Bearer {cfg_mod.settings.EDGE_AUTH_TOKEN}"},
    )


def _seed_templates(db_path: str, key_dir: str, n: int = 3):
    """Store n encrypted templates into the test DB."""
    from sentinelid_edge.services.storage.repo_templates import TemplateRepository
    repo = TemplateRepository(db_path=db_path, keychain_dir=key_dir)
    for i in range(n):
        emb = np.random.rand(128).astype(np.float32)
        repo.store_template(f"user{i}", emb)
    return repo


def _seed_audit_events(db_path: str, n: int = 5):
    """Write n audit events to the DB."""
    from sentinelid_edge.services.storage.repo_audit import AuditRepository, AuditEvent
    repo = AuditRepository(db_path=db_path)
    for i in range(n):
        event = AuditEvent(
            event_id="",
            timestamp=0,
            event_type="auth_finished",
            outcome="allow",
            reason_codes=[],
        )
        repo.write_event(event)


def _seed_outbox_events(db_path: str, n: int = 4):
    """Add n outbox events."""
    from sentinelid_edge.services.storage.repo_outbox import OutboxRepository
    repo = OutboxRepository(db_path=db_path)
    for i in range(n):
        repo.add_event({"event_id": f"evt-{i}"})


class TestDeleteIdentity:
    def test_deletes_templates(self, client, tmp_env):
        db_path, key_dir, _ = tmp_env
        _seed_templates(db_path, key_dir, n=3)
        resp = client.post("/api/v1/settings/delete_identity", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["templates_deleted"] == 3

    def test_deletes_audit_events(self, client, tmp_env):
        db_path, key_dir, _ = tmp_env
        _seed_audit_events(db_path, n=5)
        resp = client.post(
            "/api/v1/settings/delete_identity",
            json={"clear_audit": True, "clear_outbox": False, "rotate_device_key": False},
        )
        assert resp.status_code == 200
        assert resp.json()["audit_events_deleted"] == 5

    def test_deletes_outbox_events(self, client, tmp_env):
        db_path, key_dir, _ = tmp_env
        _seed_outbox_events(db_path, n=4)
        resp = client.post(
            "/api/v1/settings/delete_identity",
            json={"clear_audit": False, "clear_outbox": True, "rotate_device_key": False},
        )
        assert resp.status_code == 200
        assert resp.json()["outbox_events_deleted"] == 4

    def test_skip_audit_when_false(self, client, tmp_env):
        db_path, key_dir, _ = tmp_env
        _seed_audit_events(db_path, n=3)
        resp = client.post(
            "/api/v1/settings/delete_identity",
            json={"clear_audit": False, "clear_outbox": False, "rotate_device_key": False},
        )
        assert resp.json()["audit_events_deleted"] == 0

    def test_rotate_device_key(self, client, tmp_env):
        db_path, key_dir, _ = tmp_env
        resp = client.post(
            "/api/v1/settings/delete_identity",
            json={"clear_audit": False, "clear_outbox": False, "rotate_device_key": True},
        )
        assert resp.status_code == 200
        assert resp.json()["device_key_rotated"] is True

    def test_delete_device_key_when_rotate_false(self, client, tmp_env):
        _, _, _ = tmp_env
        from sentinelid_edge.services.security.device_binding import DeviceBinding
        from sentinelid_edge.api.v1 import settings as settings_api

        # Materialize identity metadata first.
        key_dir = settings_api.settings.KEYCHAIN_DIR
        binding = DeviceBinding(keychain_dir=key_dir)
        _ = binding.get_device_id()
        device_id_file = Path(key_dir) / "device_id.json"
        assert device_id_file.exists()

        resp = client.post(
            "/api/v1/settings/delete_identity",
            json={"clear_audit": False, "clear_outbox": False, "rotate_device_key": False},
        )
        assert resp.status_code == 200
        assert resp.json()["device_key_rotated"] is False
        assert not device_id_file.exists()

    def test_response_has_deleted_at(self, client, tmp_env):
        resp = client.post("/api/v1/settings/delete_identity", json={})
        assert resp.status_code == 200
        assert "deleted_at" in resp.json()
        assert isinstance(resp.json()["deleted_at"], int)

    def test_response_status_is_deleted(self, client, tmp_env):
        resp = client.post("/api/v1/settings/delete_identity", json={})
        assert resp.json()["status"] == "deleted"

    def test_requires_auth(self, tmp_env):
        from sentinelid_edge.main import app
        unauthenticated_client = TestClient(app)
        resp = unauthenticated_client.post("/api/v1/settings/delete_identity", json={})
        assert resp.status_code == 401
