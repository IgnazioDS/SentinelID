import pytest

from sentinelid_edge.services.telemetry.exporter import TelemetryExporter
from sentinelid_edge.services.telemetry.transport import parse_certificate_pins


def _make_exporter(tmp_path, **kwargs):
    return TelemetryExporter(
        cloud_ingest_url=kwargs.get("cloud_ingest_url", "http://127.0.0.1:8000/v1/ingest/events"),
        keychain_dir=str(tmp_path / "keys"),
        db_path=str(tmp_path / "audit.db"),
        tls_ca_bundle_path=kwargs.get("tls_ca_bundle_path"),
        mtls_cert_path=kwargs.get("mtls_cert_path"),
        mtls_key_path=kwargs.get("mtls_key_path"),
        tls_cert_sha256_pins=kwargs.get("tls_cert_sha256_pins"),
        edge_env=kwargs.get("edge_env", "dev"),
        min_pin_count_prod=kwargs.get("min_pin_count_prod", 2),
        allow_single_pin_prod=kwargs.get("allow_single_pin_prod", False),
    )


def test_http_client_kwargs_default(tmp_path):
    exporter = _make_exporter(tmp_path)
    kwargs = exporter._http_client_kwargs()
    assert kwargs["verify"] is True
    assert "cert" not in kwargs


def test_custom_ca_bundle_path_applied(tmp_path):
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("dummy-ca", encoding="utf-8")
    exporter = _make_exporter(tmp_path, tls_ca_bundle_path=str(ca_bundle))
    kwargs = exporter._http_client_kwargs()
    assert kwargs["verify"] == str(ca_bundle)


def test_invalid_ca_bundle_path_rejected(tmp_path):
    with pytest.raises(RuntimeError, match="TELEMETRY_TLS_CA_BUNDLE_PATH"):
        _make_exporter(tmp_path, tls_ca_bundle_path=str(tmp_path / "missing-ca.pem"))


def test_mtls_requires_both_cert_and_key(tmp_path):
    cert = tmp_path / "client.crt"
    cert.write_text("dummy-cert", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Both TELEMETRY_MTLS_CERT_PATH and TELEMETRY_MTLS_KEY_PATH"):
        _make_exporter(
            tmp_path,
            cloud_ingest_url="https://cloud.example.com/v1/ingest/events",
            mtls_cert_path=str(cert),
        )


def test_mtls_requires_https_url(tmp_path):
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    cert.write_text("dummy-cert", encoding="utf-8")
    key.write_text("dummy-key", encoding="utf-8")
    with pytest.raises(RuntimeError, match="requires CLOUD_INGEST_URL with https://"):
        _make_exporter(
            tmp_path,
            cloud_ingest_url="http://cloud.example.com/v1/ingest/events",
            mtls_cert_path=str(cert),
            mtls_key_path=str(key),
        )


def test_mtls_client_cert_tuple_applied(tmp_path):
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    cert.write_text("dummy-cert", encoding="utf-8")
    key.write_text("dummy-key", encoding="utf-8")
    exporter = _make_exporter(
        tmp_path,
        cloud_ingest_url="https://cloud.example.com/v1/ingest/events",
        mtls_cert_path=str(cert),
        mtls_key_path=str(key),
    )
    kwargs = exporter._http_client_kwargs()
    assert kwargs["cert"] == (str(cert), str(key))


def test_parse_certificate_pins_normalizes_variants():
    pins = parse_certificate_pins(
        "sha256:" + ":".join(["AA"] * 32) + ", " + ("22" * 32)
    )
    assert pins[0] == ("aa" * 32)
    assert pins[1] == ("22" * 32)


def test_parse_certificate_pins_deduplicates():
    pin = "33" * 32
    pins = parse_certificate_pins(f"{pin}, sha256:{pin}")
    assert pins == [pin]


def test_parse_certificate_pins_rejects_invalid_value():
    with pytest.raises(ValueError, match="Invalid certificate pin"):
        parse_certificate_pins("zzzz")


def test_tls_pins_require_https_url(tmp_path):
    pin = "11" * 32
    with pytest.raises(RuntimeError, match="requires CLOUD_INGEST_URL with https://"):
        _make_exporter(
            tmp_path,
            cloud_ingest_url="http://cloud.example.com/v1/ingest/events",
            tls_cert_sha256_pins=pin,
        )


def test_prod_pin_policy_requires_overlap_by_default(tmp_path):
    pin = "44" * 32
    with pytest.raises(RuntimeError, match="Insufficient TELEMETRY_TLS_CERT_SHA256_PINS"):
        _make_exporter(
            tmp_path,
            cloud_ingest_url="https://cloud.example.com/v1/ingest/events",
            tls_cert_sha256_pins=pin,
            edge_env="prod",
        )


def test_prod_pin_policy_allows_single_pin_when_explicit(tmp_path):
    pin = "55" * 32
    exporter = _make_exporter(
        tmp_path,
        cloud_ingest_url="https://cloud.example.com/v1/ingest/events",
        tls_cert_sha256_pins=pin,
        edge_env="prod",
        allow_single_pin_prod=True,
    )
    assert exporter is not None


def test_transport_preflight_returns_none_for_non_https(tmp_path):
    exporter = _make_exporter(tmp_path, cloud_ingest_url="http://127.0.0.1:8000/v1/ingest/events")
    assert exporter.run_transport_preflight() is None


def test_transport_preflight_returns_observed_fingerprint(tmp_path, monkeypatch):
    observed = "66" * 32
    seen = {}

    def _fake_probe(**kwargs):
        seen.update(kwargs)
        return observed

    monkeypatch.setattr(
        "sentinelid_edge.services.telemetry.exporter.probe_server_certificate_sha256",
        _fake_probe,
    )
    exporter = _make_exporter(
        tmp_path,
        cloud_ingest_url="https://cloud.example.com/v1/ingest/events",
    )
    result = exporter.run_transport_preflight(timeout_seconds=7.5)
    assert result == observed
    assert exporter.get_stats()["tls_last_observed_cert_sha256"] == observed
    assert seen["cloud_ingest_url"] == "https://cloud.example.com/v1/ingest/events"
    assert seen["timeout_seconds"] == pytest.approx(7.5)


def test_transport_preflight_rejects_pin_mismatch(tmp_path, monkeypatch):
    pin = "77" * 32
    observed = "88" * 32
    monkeypatch.setattr(
        "sentinelid_edge.services.telemetry.exporter.probe_server_certificate_sha256",
        lambda **_kwargs: observed,
    )
    exporter = _make_exporter(
        tmp_path,
        cloud_ingest_url="https://cloud.example.com/v1/ingest/events",
        tls_cert_sha256_pins=pin,
    )
    with pytest.raises(RuntimeError, match="pin mismatch"):
        exporter.run_transport_preflight()
