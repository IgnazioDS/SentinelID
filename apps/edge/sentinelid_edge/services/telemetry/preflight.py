"""Telemetry transport preflight command."""

from __future__ import annotations

from sentinelid_edge.core.config import settings
from sentinelid_edge.services.telemetry.exporter import TelemetryExporter
from sentinelid_edge.services.telemetry.transport import validate_cloud_ingest_url


def run_preflight() -> int:
    if not settings.TELEMETRY_ENABLED:
        print("telemetry preflight skipped: TELEMETRY_ENABLED=false")
        return 0
    if not settings.CLOUD_INGEST_URL:
        raise RuntimeError("telemetry preflight failed: CLOUD_INGEST_URL is empty")

    insecure = validate_cloud_ingest_url(settings.CLOUD_INGEST_URL, settings.EDGE_ENV)
    exporter = TelemetryExporter(
        cloud_ingest_url=settings.CLOUD_INGEST_URL,
        batch_size=settings.TELEMETRY_BATCH_SIZE,
        max_retries=settings.TELEMETRY_MAX_RETRIES,
        keychain_dir=settings.KEYCHAIN_DIR,
        db_path=settings.DB_PATH,
        http_timeout_seconds=settings.TELEMETRY_HTTP_TIMEOUT_SECONDS,
        tls_ca_bundle_path=settings.TELEMETRY_TLS_CA_BUNDLE_PATH,
        mtls_cert_path=settings.TELEMETRY_MTLS_CERT_PATH,
        mtls_key_path=settings.TELEMETRY_MTLS_KEY_PATH,
        tls_cert_sha256_pins=settings.TELEMETRY_TLS_CERT_SHA256_PINS,
        edge_env=settings.EDGE_ENV,
        min_pin_count_prod=settings.TELEMETRY_TLS_MIN_PIN_COUNT_PROD,
        allow_single_pin_prod=settings.TELEMETRY_TLS_ALLOW_SINGLE_PIN_PROD,
    )

    observed = exporter.run_transport_preflight(
        timeout_seconds=settings.TELEMETRY_TRANSPORT_PREFLIGHT_TIMEOUT_SECONDS
    )
    if insecure:
        print(
            "telemetry preflight warning: ingest URL is non-HTTPS for non-loopback host "
            f"in {settings.EDGE_ENV} mode: {settings.CLOUD_INGEST_URL}"
        )
    if observed:
        print(f"telemetry preflight passed: server_cert_sha256={observed}")
    else:
        print("telemetry preflight passed: non-HTTPS ingest URL (no TLS handshake check)")
    return 0


def main() -> int:
    return run_preflight()


if __name__ == "__main__":
    raise SystemExit(main())
