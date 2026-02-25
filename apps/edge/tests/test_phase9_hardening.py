from __future__ import annotations

import time
import tempfile

from fastapi.testclient import TestClient

import sentinelid_edge.core.auth as auth_mod
from sentinelid_edge.main import app
from sentinelid_edge.services.observability.perf import PerfRegistry
from sentinelid_edge.services.processing.frame_control import FrameProcessingController


def test_frame_controller_rate_cap() -> None:
    controller = FrameProcessingController(max_fps=10.0, state_ttl_seconds=120)
    allowed, reason = controller.try_acquire("s1")
    assert allowed is True
    assert reason is None
    controller.release("s1", processed=True)

    # Immediate next frame should be rate-capped at 10 fps.
    allowed, reason = controller.try_acquire("s1")
    assert allowed is False
    assert reason == "rate_capped"


def test_frame_controller_backpressure_drop() -> None:
    controller = FrameProcessingController(max_fps=100.0, state_ttl_seconds=120)
    first_allowed, _ = controller.try_acquire("s2")
    assert first_allowed is True

    second_allowed, reason = controller.try_acquire("s2")
    assert second_allowed is False
    assert reason == "queue_backed_up"
    controller.release("s2", processed=False)


def test_frame_controller_snapshot_contains_drop_counters() -> None:
    controller = FrameProcessingController(max_fps=5.0, state_ttl_seconds=120)
    allowed, _ = controller.try_acquire("s3")
    assert allowed is True
    denied, _ = controller.try_acquire("s3")
    assert denied is False
    controller.release("s3", processed=True)
    snap = controller.snapshot()
    assert snap["processed_total"] == 1
    assert snap["dropped_backpressure_total"] == 1


def test_perf_registry_snapshot_has_percentiles() -> None:
    registry = PerfRegistry(window_size=20)
    for value in [1.0, 2.0, 3.0, 4.0, 10.0]:
        registry.observe_ms("stage.x", value)

    snap = registry.snapshot()["stage.x"]
    assert snap["count"] == 5
    assert snap["p50_ms"] is not None
    assert snap["p95_ms"] is not None
    assert snap["max_ms"] == 10.0


def test_perf_registry_stage_context_manager_records_time() -> None:
    registry = PerfRegistry(window_size=5)
    with registry.stage("stage.y"):
        time.sleep(0.002)
    snap = registry.snapshot()["stage.y"]
    assert snap["count"] == 1
    assert snap["mean_ms"] is not None
    assert snap["mean_ms"] > 0.0


def test_v1_health_endpoint_is_public() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_diagnostics_includes_perf_and_frame_processing_sections() -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/diagnostics",
        headers={"Authorization": f"Bearer {auth_mod.settings.EDGE_AUTH_TOKEN}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "performance" in data
    assert "frame_processing" in data
    assert "outbox_pending_count" in data
    assert "dlq_count" in data
    assert "last_error_summary" in data
    assert "telemetry_flags" in data


def test_telemetry_settings_endpoint_handles_runtime_absent(monkeypatch) -> None:
    import sentinelid_edge.api.v1.settings as settings_api

    monkeypatch.setattr(settings_api, "get_telemetry_runtime", lambda: None)
    client = TestClient(app)

    resp = client.get(
        "/api/v1/settings/telemetry",
        headers={"Authorization": f"Bearer {auth_mod.settings.EDGE_AUTH_TOKEN}"},
    )
    assert resp.status_code == 200
    assert resp.json()["runtime_available"] is False

    update_resp = client.post(
        "/api/v1/settings/telemetry",
        headers={"Authorization": f"Bearer {auth_mod.settings.EDGE_AUTH_TOKEN}"},
        json={"telemetry_enabled": True},
    )
    assert update_resp.status_code == 409


def test_telemetry_settings_endpoint_updates_runtime(monkeypatch) -> None:
    import sentinelid_edge.api.v1.settings as settings_api

    class _Runtime:
        def __init__(self):
            self.enabled = False

        def set_enabled(self, enabled: bool) -> None:
            self.enabled = bool(enabled)

    runtime = _Runtime()
    monkeypatch.setattr(settings_api, "get_telemetry_runtime", lambda: runtime)
    client = TestClient(app)

    update_resp = client.post(
        "/api/v1/settings/telemetry",
        headers={"Authorization": f"Bearer {auth_mod.settings.EDGE_AUTH_TOKEN}"},
        json={"telemetry_enabled": True},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["telemetry_enabled"] is True


def test_admin_replay_dlq_endpoint_requeues_event(monkeypatch) -> None:
    from sentinelid_edge.services.storage.repo_outbox import OutboxRepository

    with tempfile.TemporaryDirectory(prefix="edge_dlq_replay_") as tmpdir:
        db_path = f"{tmpdir}/audit.db"
        monkeypatch.setattr(auth_mod.settings, "DB_PATH", db_path)

        repo = OutboxRepository(db_path)
        event_id = repo.add_event({"event_id": "dlq-test"})
        for _ in range(3):
            repo.mark_failed_with_error(
                event_id,
                "cloud unavailable",
                max_attempts=3,
                initial_backoff_seconds=0.1,
                jitter_ratio=0.0,
            )

        assert len(repo.get_dlq_events()) == 1
        client = TestClient(app)
        resp = client.post(
            "/api/v1/admin/outbox/replay-dlq",
            headers={"Authorization": f"Bearer {auth_mod.settings.EDGE_AUTH_TOKEN}"},
            json={"event_id": event_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "replayed"
        assert body["replayed_count"] == 1
        assert len(repo.get_dlq_events()) == 0
