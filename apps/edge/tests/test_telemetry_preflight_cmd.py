import pytest

from sentinelid_edge.services.telemetry import preflight as preflight_mod


def _set_preflight_settings(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    defaults = {
        "TELEMETRY_ENABLED": True,
        "CLOUD_INGEST_URL": "http://cloud.example.com/v1/ingest/events",
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
        "TELEMETRY_TRANSPORT_PREFLIGHT_TIMEOUT_SECONDS": 5.0,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(preflight_mod.settings, key, value)


def test_preflight_skips_when_telemetry_disabled(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _set_preflight_settings(monkeypatch, TELEMETRY_ENABLED=False)
    assert preflight_mod.run_preflight() == 0
    out = capsys.readouterr().out
    assert "skipped" in out


def test_preflight_warns_on_insecure_transport(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _set_preflight_settings(monkeypatch)

    class _FakeExporter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_transport_preflight(self, timeout_seconds: float):
            return None

    monkeypatch.setattr(preflight_mod, "TelemetryExporter", _FakeExporter)
    monkeypatch.setattr(preflight_mod, "validate_cloud_ingest_url", lambda _url, _env: True)

    assert preflight_mod.run_preflight() == 0
    out = capsys.readouterr().out
    assert "warning" in out
    assert "non-HTTPS ingest URL" in out


def test_preflight_prints_observed_cert(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    observed = "99" * 32
    _set_preflight_settings(
        monkeypatch,
        CLOUD_INGEST_URL="https://cloud.example.com/v1/ingest/events",
    )

    class _FakeExporter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_transport_preflight(self, timeout_seconds: float):
            return observed

    monkeypatch.setattr(preflight_mod, "TelemetryExporter", _FakeExporter)
    monkeypatch.setattr(preflight_mod, "validate_cloud_ingest_url", lambda _url, _env: False)

    assert preflight_mod.run_preflight() == 0
    out = capsys.readouterr().out
    assert observed in out
