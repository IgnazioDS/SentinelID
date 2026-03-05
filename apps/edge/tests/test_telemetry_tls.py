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
