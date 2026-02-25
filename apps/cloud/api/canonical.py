"""Canonical telemetry JSON serialization for signatures."""
from __future__ import annotations

import json
from typing import Any, Dict, List


def canonical_json_bytes(payload: Any) -> bytes:
    """Return canonical JSON bytes for telemetry signing and verification.

    Canonical representation is strict UTF-8 JSON with:
    - sorted object keys
    - no insignificant whitespace

    Both edge signer and cloud verifier must hash/sign these exact bytes.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def event_payload_for_signature(event_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return canonical signable event payload (exclude mutable signature field)."""
    payload = dict(event_payload)
    payload.pop("signature", None)
    return payload


def batch_payload_for_signature(
    batch_id: str,
    device_id: str,
    timestamp: int,
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return canonical signable batch payload."""
    return {
        "batch_id": batch_id,
        "device_id": device_id,
        "timestamp": timestamp,
        "events": events,
    }
