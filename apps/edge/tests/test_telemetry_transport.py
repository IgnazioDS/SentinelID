import pytest

from sentinelid_edge.services.telemetry.transport import validate_cloud_ingest_url


def test_https_external_allowed_in_prod() -> None:
    insecure = validate_cloud_ingest_url("https://cloud.example.com/v1/ingest/events", "prod")
    assert insecure is False


def test_http_loopback_allowed_in_prod() -> None:
    insecure = validate_cloud_ingest_url("http://127.0.0.1:8000/v1/ingest/events", "prod")
    assert insecure is False


def test_http_external_rejected_in_prod() -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        validate_cloud_ingest_url("http://cloud.example.com/v1/ingest/events", "prod")


def test_http_external_allowed_with_warning_signal_in_dev() -> None:
    insecure = validate_cloud_ingest_url("http://cloud.example.com/v1/ingest/events", "dev")
    assert insecure is True


def test_invalid_scheme_rejected() -> None:
    with pytest.raises(ValueError, match="must use http:// or https://"):
        validate_cloud_ingest_url("ftp://cloud.example.com/v1/ingest/events", "prod")
