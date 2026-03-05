from __future__ import annotations

from fastapi.testclient import TestClient

import sentinelid_edge.main as main_mod


def _set_telemetry_startup_settings(monkeypatch, **overrides) -> None:
    defaults = {
        "TELEMETRY_ENABLED": True,
        "CLOUD_INGEST_URL": "http://127.0.0.1:8000/v1/ingest/events",
        "EDGE_ENV": "dev",
        "TELEMETRY_BATCH_SIZE": 10,
        "TELEMETRY_MAX_RETRIES": 3,
        "KEYCHAIN_DIR": ".sentinelid/keys",
        "DB_PATH": ".sentinelid/audit.db",
        "TELEMETRY_HTTP_TIMEOUT_SECONDS": 10.0,
        "TELEMETRY_TLS_CA_BUNDLE_PATH": "",
        "TELEMETRY_MTLS_CERT_PATH": "",
        "TELEMETRY_MTLS_KEY_PATH": "",
        "TELEMETRY_TLS_CERT_SHA256_PINS": "",
        "TELEMETRY_TLS_MIN_PIN_COUNT_PROD": 2,
        "TELEMETRY_TLS_ALLOW_SINGLE_PIN_PROD": False,
        "TELEMETRY_EXPORT_INTERVAL_SECONDS": 1.5,
        "TELEMETRY_SIGNAL_QUEUE_SIZE": 256,
        "TELEMETRY_TRANSPORT_PREFLIGHT_ON_START": False,
        "TELEMETRY_TRANSPORT_PREFLIGHT_TIMEOUT_SECONDS": 5.0,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(main_mod.settings, key, value)


def test_startup_skips_transport_preflight_when_flag_disabled(monkeypatch) -> None:
    _set_telemetry_startup_settings(
        monkeypatch,
        TELEMETRY_TRANSPORT_PREFLIGHT_ON_START=False,
    )
    preflight_calls = []
    runtime_started = []
    runtime_stopped = []

    class _FakeExporter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_transport_preflight(self, timeout_seconds: float = 5.0):
            preflight_calls.append(timeout_seconds)
            return "aa" * 32

    class _FakeRuntime:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def start(self):
            runtime_started.append(True)

        async def stop(self):
            runtime_stopped.append(True)

    monkeypatch.setattr(main_mod, "TelemetryExporter", _FakeExporter)
    monkeypatch.setattr(main_mod, "TelemetryRuntime", _FakeRuntime)
    monkeypatch.setattr(main_mod, "validate_cloud_ingest_url", lambda _url, _env: False)

    with TestClient(main_mod.app):
        pass

    assert preflight_calls == []
    assert runtime_started == [True]
    assert runtime_stopped == [True]


def test_startup_runs_transport_preflight_when_flag_enabled(monkeypatch) -> None:
    _set_telemetry_startup_settings(
        monkeypatch,
        TELEMETRY_TRANSPORT_PREFLIGHT_ON_START=True,
        TELEMETRY_TRANSPORT_PREFLIGHT_TIMEOUT_SECONDS=8.25,
    )
    preflight_calls = []

    class _FakeExporter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_transport_preflight(self, timeout_seconds: float = 5.0):
            preflight_calls.append(timeout_seconds)
            return "bb" * 32

    class _FakeRuntime:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def start(self):
            return None

        async def stop(self):
            return None

    monkeypatch.setattr(main_mod, "TelemetryExporter", _FakeExporter)
    monkeypatch.setattr(main_mod, "TelemetryRuntime", _FakeRuntime)
    monkeypatch.setattr(main_mod, "validate_cloud_ingest_url", lambda _url, _env: False)

    with TestClient(main_mod.app):
        pass

    assert preflight_calls == [8.25]
