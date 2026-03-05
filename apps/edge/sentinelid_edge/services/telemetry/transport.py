"""Telemetry transport policy helpers."""

from __future__ import annotations

import hashlib
import ipaddress
import socket
import ssl
from urllib.parse import urlparse


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() in {"localhost", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_cloud_ingest_url(cloud_ingest_url: str, edge_env: str) -> bool:
    """
    Validate telemetry ingest transport policy.

    Rules:
    - URL must be absolute HTTP(S).
    - In production, non-loopback endpoints must use HTTPS.

    Returns:
        True when URL uses insecure HTTP to a non-loopback host.
    """
    parsed = urlparse(cloud_ingest_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("CLOUD_INGEST_URL must use http:// or https://")
    if not parsed.netloc:
        raise ValueError("CLOUD_INGEST_URL must be an absolute URL")

    host = parsed.hostname
    if not host:
        raise ValueError("CLOUD_INGEST_URL host is missing")

    if parsed.scheme == "https":
        return False

    if _is_loopback_host(host):
        return False

    if str(edge_env).strip().lower() == "prod":
        raise ValueError(
            "CLOUD_INGEST_URL must use HTTPS in production unless the host is loopback"
        )
    return True


def parse_certificate_pins(raw: str | None) -> list[str]:
    """
    Parse comma-separated SHA-256 cert fingerprint pins.

    Accepted forms per pin:
    - 64 hex chars
    - hex with ":" separators
    - optional "sha256:" prefix
    """
    if not raw:
        return []
    pins: list[str] = []
    for chunk in str(raw).split(","):
        token = chunk.strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered.startswith("sha256:"):
            token = token[len("sha256:") :]
        normalized = token.replace(":", "").strip().lower()
        if len(normalized) != 64:
            raise ValueError(f"Invalid certificate pin length: {chunk.strip()!r}")
        try:
            int(normalized, 16)
        except ValueError as exc:
            raise ValueError(f"Invalid certificate pin hex value: {chunk.strip()!r}") from exc
        if normalized not in pins:
            pins.append(normalized)
    return pins


def validate_pin_rollout_policy(
    *,
    pins: list[str],
    edge_env: str,
    min_pin_count_prod: int = 2,
    allow_single_pin_prod: bool = False,
) -> None:
    """
    Validate operational policy for certificate pin rollout.

    In production, pinning should keep at least two active pins to support
    certificate rotation overlap. Single-pin mode can be explicitly allowed
    for bootstrapping.
    """
    if not pins:
        return
    if str(edge_env).strip().lower() != "prod":
        return
    required = max(1, int(min_pin_count_prod))
    if allow_single_pin_prod:
        required = 1
    if len(pins) < required:
        raise ValueError(
            "Insufficient TELEMETRY_TLS_CERT_SHA256_PINS for production rollout: "
            f"have={len(pins)} required={required}"
        )


def validate_server_certificate_pin(
    *,
    cloud_ingest_url: str,
    expected_pins: list[str],
    tls_ca_bundle_path: str | None,
    mtls_cert_path: str | None,
    mtls_key_path: str | None,
    timeout_seconds: float = 5.0,
) -> str:
    """
    Validate remote server certificate fingerprint against expected pins.

    Returns:
        Observed certificate SHA-256 fingerprint (hex, lowercase).
    """
    observed = probe_server_certificate_sha256(
        cloud_ingest_url=cloud_ingest_url,
        tls_ca_bundle_path=tls_ca_bundle_path,
        mtls_cert_path=mtls_cert_path,
        mtls_key_path=mtls_key_path,
        timeout_seconds=timeout_seconds,
    )
    expected = {pin.lower() for pin in expected_pins}
    if observed not in expected:
        raise ValueError(
            "Server certificate pin mismatch: "
            f"observed={observed} expected_one_of={sorted(expected)}"
        )
    return observed


def probe_server_certificate_sha256(
    *,
    cloud_ingest_url: str,
    tls_ca_bundle_path: str | None,
    mtls_cert_path: str | None,
    mtls_key_path: str | None,
    timeout_seconds: float = 5.0,
) -> str:
    """
    Probe remote HTTPS endpoint certificate and return SHA-256 fingerprint.
    """
    parsed = urlparse(cloud_ingest_url)
    if parsed.scheme.lower() != "https":
        raise ValueError("Certificate probing requires CLOUD_INGEST_URL with https://")
    host = parsed.hostname
    if not host:
        raise ValueError("CLOUD_INGEST_URL host is missing")
    port = parsed.port or 443

    context = ssl.create_default_context(cafile=tls_ca_bundle_path or None)
    if mtls_cert_path or mtls_key_path:
        if not (mtls_cert_path and mtls_key_path):
            raise ValueError("mTLS probe requires both cert and key paths")
        context.load_cert_chain(certfile=mtls_cert_path, keyfile=mtls_key_path)

    with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls_sock:
            cert_der = tls_sock.getpeercert(binary_form=True)
            if not cert_der:
                raise ValueError("Unable to read peer certificate during TLS preflight")

    return hashlib.sha256(cert_der).hexdigest().lower()
