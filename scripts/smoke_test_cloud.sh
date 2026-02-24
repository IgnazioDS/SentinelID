#!/usr/bin/env bash
set -euo pipefail

CLOUD_URL="${CLOUD_URL:-http://127.0.0.1:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-dev-admin-token}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/apps/edge/.venv/bin/python}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

echo "Running cloud smoke test against ${CLOUD_URL}"

"${PYTHON_BIN}" - "${REPO_ROOT}" "${CLOUD_URL}" "${ADMIN_TOKEN}" <<'PY'
from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

repo_root = Path(sys.argv[1])
cloud_url = sys.argv[2].rstrip("/")
admin_token = sys.argv[3]

sys.path.insert(0, str(repo_root / "apps" / "edge"))

from sentinelid_edge.services.telemetry.event import TelemetryBatch, TelemetryEvent
from sentinelid_edge.services.telemetry.signer import TelemetrySigner


def request(method: str, path: str, payload: dict | None = None, headers: dict | None = None) -> dict:
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{cloud_url}{path}",
        method=method,
        data=data,
        headers=req_headers,
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


with tempfile.TemporaryDirectory(prefix="sentinelid_smoke_cloud_") as keychain_dir:
    signer = TelemetrySigner(keychain_dir=keychain_dir)
    event = TelemetryEvent(
        event_id=str(uuid.uuid4()),
        device_id=signer.get_device_id(),
        timestamp=int(time.time()),
        event_type="auth_finished",
        outcome="allow",
        reason_codes=["LIVENESS_PASSED"],
        liveness_passed=True,
        similarity_score=0.91,
        risk_score=0.08,
        session_duration_seconds=2,
    )
    signer.sign_event(event)

    batch = TelemetryBatch(
        batch_id=str(uuid.uuid4()),
        device_id=signer.get_device_id(),
        timestamp=int(time.time()),
        events=[event],
    )
    signer.sign_batch(batch)

    ingest_payload = {
        "batch_id": batch.batch_id,
        "device_id": batch.device_id,
        "timestamp": batch.timestamp,
        "device_public_key": signer.get_public_key(),
        "batch_signature": batch.signature,
        "events": [
            {
                "event_id": event.event_id,
                "device_id": event.device_id,
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "outcome": event.outcome,
                "reason_codes": event.reason_codes,
                "liveness_passed": event.liveness_passed,
                "similarity_score": event.similarity_score,
                "risk_score": event.risk_score,
                "session_duration_seconds": event.session_duration_seconds,
                "audit_event_hash": event.audit_event_hash,
                "signature": event.signature,
            }
        ],
    }

    ingest = request("POST", "/v1/ingest/events", ingest_payload)
    assert ingest.get("status") == "accepted", f"Ingest failed: {ingest}"

stats = request("GET", "/v1/admin/stats", headers={"X-Admin-Token": admin_token})
events = request("GET", "/v1/admin/events?limit=1", headers={"X-Admin-Token": admin_token})
devices = request("GET", "/v1/admin/devices?limit=1", headers={"X-Admin-Token": admin_token})

assert "total_events" in stats, f"Stats missing fields: {stats}"
assert "latency_p50_ms" in stats, f"Latency metrics missing: {stats}"
assert "risk_distribution" in stats, f"Risk distribution missing: {stats}"
assert "events" in events and "has_next" in events, f"Events pagination missing: {events}"
assert "devices" in devices and "has_next" in devices, f"Devices pagination missing: {devices}"

print("Cloud smoke test passed")
PY
