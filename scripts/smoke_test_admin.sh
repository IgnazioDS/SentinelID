#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_TOKEN:-}}"

if [[ -z "${ADMIN_TOKEN}" ]]; then
  echo "ADMIN_TOKEN (or ADMIN_API_TOKEN) is required"
  exit 1
fi

echo "Running admin smoke test against ${API_URL}"

for _ in $(seq 1 80); do
  if curl -fsS "${API_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS "${API_URL}/health" >/dev/null 2>&1; then
  echo "Admin API upstream did not become healthy at ${API_URL}/health"
  exit 1
fi

python3 - "${API_URL}" "${ADMIN_TOKEN}" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

api_url = sys.argv[1].rstrip("/")
admin_token = sys.argv[2]


def request(path: str, token: str | None = None) -> tuple[int, dict | str]:
    headers = {}
    if token is not None:
        headers["X-Admin-Token"] = token
    req = urllib.request.Request(f"{api_url}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return exc.code, parsed


status, devices = request("/v1/admin/devices?limit=5", admin_token)
assert status == 200, f"/devices unexpected status {status}: {devices}"
assert isinstance(devices.get("devices"), list), f"/devices payload invalid: {devices}"
assert "has_next" in devices, f"/devices pagination missing: {devices}"

status, events = request("/v1/admin/events?limit=5", admin_token)
assert status == 200, f"/events unexpected status {status}: {events}"
assert isinstance(events.get("events"), list), f"/events payload invalid: {events}"
assert "has_next" in events, f"/events pagination missing: {events}"

status, stats = request("/v1/admin/stats", admin_token)
assert status == 200, f"/stats unexpected status {status}: {stats}"
for field in ("total_devices", "total_events", "latency_p50_ms", "latency_p95_ms", "risk_distribution"):
    assert field in stats, f"/stats missing {field}: {stats}"

status, no_auth = request("/v1/admin/devices")
assert status == 401, f"/devices without token expected 401, got {status}: {no_auth}"

status, bad_auth = request("/v1/admin/devices", "invalid-token")
assert status == 401, f"/devices invalid token expected 401, got {status}: {bad_auth}"

print("Admin smoke test passed")
PY
