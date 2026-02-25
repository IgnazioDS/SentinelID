"""Canonical telemetry JSON serialization for signatures."""
from __future__ import annotations

import json
from typing import Any


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
