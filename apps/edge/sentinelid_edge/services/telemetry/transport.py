"""Telemetry transport policy helpers."""

from __future__ import annotations

import ipaddress
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
