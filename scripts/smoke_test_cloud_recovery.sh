#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/compose_env_file.sh
source "${SCRIPT_DIR}/lib/compose_env_file.sh"
prepare_compose_env_file "${REPO_ROOT}"

if [[ -z "${EDGE_URL:-}" ]]; then
  EDGE_PORT_AUTO="$(
    python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
  )"
  EDGE_URL="http://127.0.0.1:${EDGE_PORT_AUTO}"
else
  EDGE_URL="${EDGE_URL}"
fi
EDGE_TOKEN="${EDGE_TOKEN:-${EDGE_AUTH_TOKEN:-devtoken}}"
CLOUD_URL="${CLOUD_URL:-http://127.0.0.1:8000}"
CLOUD_INGEST_URL="${CLOUD_INGEST_URL:-${CLOUD_URL}/v1/ingest/events}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_TOKEN:-}}"
RECOVERY_CLOUD_BIND_HOST="${RECOVERY_CLOUD_BIND_HOST:-0.0.0.0}"
RECOVERY_EDGE_HEALTH_TIMEOUT_SECONDS="${RECOVERY_EDGE_HEALTH_TIMEOUT_SECONDS:-60}"
DIAG_DIR="${SMOKE_RECOVERY_DIAG_DIR:-${REPO_ROOT}/output/ci/logs}"

if [[ -z "${EDGE_TOKEN}" ]]; then
  echo "EDGE_TOKEN (or EDGE_AUTH_TOKEN) is required"
  exit 1
fi

if [[ -z "${ADMIN_TOKEN}" ]]; then
  echo "ADMIN_TOKEN (or ADMIN_API_TOKEN) is required"
  exit 1
fi

EDGE_HOST="$(python3 - "${EDGE_URL}" <<'PY'
from urllib.parse import urlparse
import sys
print(urlparse(sys.argv[1]).hostname or '127.0.0.1')
PY
)"
EDGE_PORT="$(python3 - "${EDGE_URL}" <<'PY'
from urllib.parse import urlparse
import sys
u=urlparse(sys.argv[1])
print(u.port or 8787)
PY
)"

EDGE_LOG="$(mktemp -t sentinelid_cloud_recovery_edge.XXXXXX.log)"
EDGE_PID=""
STATE_DIR="$(mktemp -d -t sentinelid_cloud_recovery_state.XXXXXX)"
EDGE_DB_PATH="${STATE_DIR}/audit.db"
EDGE_KEYCHAIN_DIR="${STATE_DIR}/keys"

cleanup() {
  if [[ -n "${EDGE_PID}" ]] && kill -0 "${EDGE_PID}" >/dev/null 2>&1; then
    kill "${EDGE_PID}" >/dev/null 2>&1 || true
    wait "${EDGE_PID}" >/dev/null 2>&1 || true
  fi
  pkill -f "sentinelid_edge.main:app --host ${EDGE_HOST} --port ${EDGE_PORT}" >/dev/null 2>&1 || true
  rm -rf "${STATE_DIR}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

dump_recovery_diagnostics() {
  mkdir -p "${DIAG_DIR}"
  local ts
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  local prefix="${DIAG_DIR}/cloud_recovery_failure_${ts}"
  echo "[recovery] writing failure diagnostics to ${prefix}_*.txt"
  {
    echo "edge_url=${EDGE_URL}"
    echo "cloud_url=${CLOUD_URL}"
    echo "cloud_ingest_url=${CLOUD_INGEST_URL}"
    echo "recovery_cloud_bind_host=${RECOVERY_CLOUD_BIND_HOST}"
  } > "${prefix}_summary.txt"
  if [[ -f "${EDGE_LOG}" ]]; then
    tail -n 200 "${EDGE_LOG}" > "${prefix}_edge_tail.log" 2>&1 || true
  fi
  compose_cmd ps > "${prefix}_compose_ps.txt" 2>&1 || true
  compose_cmd logs --no-color > "${prefix}_compose.log" 2>&1 || true
}

trap dump_recovery_diagnostics ERR

echo "[recovery] stopping cloud/admin to simulate outage"
compose_cmd stop cloud admin >/dev/null 2>&1 || true

echo "[recovery] ensuring postgres is running"
compose_cmd up -d postgres >/dev/null

echo "[recovery] starting edge with telemetry enabled"
(
  cd "${REPO_ROOT}/apps/edge"
  if [[ -x .venv/bin/python ]]; then
    EDGE_ENV=dev ALLOW_FALLBACK_EMBEDDINGS=1 TELEMETRY_ENABLED=true \
      TELEMETRY_MAX_RETRIES=20 TELEMETRY_BATCH_SIZE=1 TELEMETRY_EXPORT_INTERVAL_SECONDS=0.5 \
      CLOUD_INGEST_URL="${CLOUD_INGEST_URL}" EDGE_HOST="${EDGE_HOST}" EDGE_PORT="${EDGE_PORT}" \
      SENTINELID_DB_PATH="${EDGE_DB_PATH}" SENTINELID_KEYCHAIN_DIR="${EDGE_KEYCHAIN_DIR}" \
      EDGE_AUTH_TOKEN="${EDGE_TOKEN}" .venv/bin/python -m uvicorn sentinelid_edge.main:app --host "${EDGE_HOST}" --port "${EDGE_PORT}" >"${EDGE_LOG}" 2>&1
  elif command -v poetry >/dev/null 2>&1; then
    EDGE_ENV=dev ALLOW_FALLBACK_EMBEDDINGS=1 TELEMETRY_ENABLED=true \
      TELEMETRY_MAX_RETRIES=20 TELEMETRY_BATCH_SIZE=1 TELEMETRY_EXPORT_INTERVAL_SECONDS=0.5 \
      CLOUD_INGEST_URL="${CLOUD_INGEST_URL}" EDGE_HOST="${EDGE_HOST}" EDGE_PORT="${EDGE_PORT}" \
      SENTINELID_DB_PATH="${EDGE_DB_PATH}" SENTINELID_KEYCHAIN_DIR="${EDGE_KEYCHAIN_DIR}" \
      EDGE_AUTH_TOKEN="${EDGE_TOKEN}" poetry run uvicorn sentinelid_edge.main:app --host "${EDGE_HOST}" --port "${EDGE_PORT}" >"${EDGE_LOG}" 2>&1
  elif [[ -x .venv/bin/poetry ]]; then
    EDGE_ENV=dev ALLOW_FALLBACK_EMBEDDINGS=1 TELEMETRY_ENABLED=true \
      TELEMETRY_MAX_RETRIES=20 TELEMETRY_BATCH_SIZE=1 TELEMETRY_EXPORT_INTERVAL_SECONDS=0.5 \
      CLOUD_INGEST_URL="${CLOUD_INGEST_URL}" EDGE_HOST="${EDGE_HOST}" EDGE_PORT="${EDGE_PORT}" \
      SENTINELID_DB_PATH="${EDGE_DB_PATH}" SENTINELID_KEYCHAIN_DIR="${EDGE_KEYCHAIN_DIR}" \
      EDGE_AUTH_TOKEN="${EDGE_TOKEN}" .venv/bin/poetry run uvicorn sentinelid_edge.main:app --host "${EDGE_HOST}" --port "${EDGE_PORT}" >"${EDGE_LOG}" 2>&1
  else
    echo "Edge runtime not found (.venv/bin/python or poetry)"
    exit 1
  fi
) &
EDGE_PID=$!

for _ in $(seq 1 $((RECOVERY_EDGE_HEALTH_TIMEOUT_SECONDS * 4))); do
  if curl -fsS "${EDGE_URL}/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${EDGE_PID}" >/dev/null 2>&1; then
    echo "Edge exited before becoming healthy"
    tail -n 120 "${EDGE_LOG}" || true
    exit 1
  fi
  sleep 0.25
done

if ! curl -fsS "${EDGE_URL}/api/v1/health" >/dev/null 2>&1; then
  echo "Edge did not become healthy"
  tail -n 120 "${EDGE_LOG}" || true
  exit 1
fi

EDGE_REQ_ID="$(curl -sS -D - -o /dev/null "${EDGE_URL}/api/v1/health" | tr -d '\r' | awk 'tolower($1)=="x-request-id:"{print $2}' | tail -n 1)"
if [[ -z "${EDGE_REQ_ID}" ]]; then
  echo "Missing X-Request-Id in edge health response"
  exit 1
fi
echo "[recovery] edge request_id=${EDGE_REQ_ID}"

echo "[recovery] running local auth while cloud is down"
python3 - "${EDGE_URL}" "${EDGE_TOKEN}" <<'PY'
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

edge_url = sys.argv[1].rstrip("/")
token = sys.argv[2]

FRAME_DATA_URL = (
    "data:image/jpeg;base64,"
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxISEhUTEhIVFhUXFRUVFRUVFRUVFRUXFhUX"
    "FhUVFRUYHSggGBolHRUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0lHyUtLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMB"
    "IgACEQEDEQH/xAAXAAADAQAAAAAAAAAAAAAAAAAAAQID/8QAFhABAQEAAAAAAAAAAAAAAAAA"
    "AAER/8QAFgEBAQEAAAAAAAAAAAAAAAAAAgAB/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwD"
    "AQACEQMRAD8A0wD/AP/Z"
)


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{edge_url}{path}",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


start = post("/api/v1/auth/start", {})
session_id = start["session_id"]

for _ in range(10):
    post("/api/v1/auth/frame", {"session_id": session_id, "frame": FRAME_DATA_URL})
    time.sleep(0.11)

finish = post("/api/v1/auth/finish", {"session_id": session_id})
if finish.get("decision") == "step_up":
    for _ in range(10):
        post("/api/v1/auth/frame", {"session_id": session_id, "frame": FRAME_DATA_URL})
        time.sleep(0.11)
    finish = post("/api/v1/auth/finish", {"session_id": session_id})

if finish.get("decision") not in {"allow", "deny"}:
    raise SystemExit(f"unexpected auth finish response: {finish}")

print("auth_completed", finish["decision"])
PY

echo "[recovery] asserting outbox has pending events"
PENDING_COUNT=0
DLQ_COUNT=0
for _ in $(seq 1 40); do
  COUNTS="$(python3 - "${EDGE_URL}" "${EDGE_TOKEN}" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.request

edge_url = sys.argv[1].rstrip("/")
token = sys.argv[2]
req = urllib.request.Request(
    f"{edge_url}/api/v1/diagnostics",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    body = json.loads(resp.read().decode("utf-8"))
outbox = body.get("outbox", {})
pending = max(
    int(body.get("outbox_pending_count", 0)),
    int(outbox.get("pending_count", 0)),
)
dlq = max(
    int(body.get("dlq_count", 0)),
    int(outbox.get("dlq_count", 0)),
)
print(f"{pending},{dlq}")
PY
)"
  PENDING_COUNT="${COUNTS%%,*}"
  DLQ_COUNT="${COUNTS##*,}"
  if [[ "${PENDING_COUNT}" -gt 0 || "${DLQ_COUNT}" -gt 0 ]]; then
    break
  fi
  sleep 0.5
done

if [[ "${PENDING_COUNT}" -le 0 && "${DLQ_COUNT}" -le 0 ]]; then
  echo "Expected buffered events while cloud is down, got pending=${PENDING_COUNT} dlq=${DLQ_COUNT}"
  tail -n 120 "${EDGE_LOG}" || true
  exit 1
fi

echo "[recovery] starting cloud/admin and waiting for recovery"
CLOUD_BIND_HOST="${RECOVERY_CLOUD_BIND_HOST}" compose_cmd up -d cloud admin >/dev/null

for _ in $(seq 1 120); do
  if curl -fsS "${CLOUD_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS "${CLOUD_URL}/health" >/dev/null 2>&1; then
  echo "Cloud did not become healthy"
  echo "[recovery] docker compose ps"
  compose_cmd ps || true
  echo "[recovery] cloud logs (tail 120)"
  compose_cmd logs --tail=120 cloud || true
  exit 1
fi

CLOUD_REQ_ID="$(curl -sS -D - -o /dev/null "${CLOUD_URL}/health" | tr -d '\r' | awk 'tolower($1)=="x-request-id:"{print $2}' | tail -n 1)"
if [[ -z "${CLOUD_REQ_ID}" ]]; then
  echo "Missing X-Request-Id in cloud health response"
  exit 1
fi
echo "[recovery] cloud request_id=${CLOUD_REQ_ID}"

for _ in $(seq 1 120); do
  counts="$(python3 - "${EDGE_URL}" "${EDGE_TOKEN}" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.request

edge_url = sys.argv[1].rstrip("/")
token = sys.argv[2]
req = urllib.request.Request(
    f"{edge_url}/api/v1/diagnostics",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    body = json.loads(resp.read().decode("utf-8"))
outbox = body.get("outbox", {})
print(f"{int(outbox.get('pending_count', 0))},{int(outbox.get('sent_count', 0))}")
PY
)"
  pending="${counts%%,*}"
  sent="${counts##*,}"
  if [[ "${pending}" -eq 0 && "${sent}" -gt 0 ]]; then
    break
  fi
  sleep 0.5
done

if [[ "${pending}" -ne 0 ]]; then
  echo "Outbox did not drain after cloud recovery (pending=${pending}, sent=${sent})"
  python3 - "${EDGE_URL}" "${EDGE_TOKEN}" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.request

edge_url = sys.argv[1].rstrip("/")
token = sys.argv[2]
req = urllib.request.Request(
    f"{edge_url}/api/v1/diagnostics",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    body = json.loads(resp.read().decode("utf-8"))
print("Diagnostics snapshot:", json.dumps(body, indent=2))
PY
  tail -n 120 "${EDGE_LOG}" || true
  exit 1
fi

EVENT_COUNT="$(python3 - "${CLOUD_URL}" "${ADMIN_TOKEN}" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.request

cloud_url = sys.argv[1].rstrip("/")
admin_token = sys.argv[2]
req = urllib.request.Request(
    f"{cloud_url}/v1/admin/events?limit=5",
    headers={"X-Admin-Token": admin_token},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    body = json.loads(resp.read().decode("utf-8"))
print(len(body.get("events", [])))
PY
)"

if [[ "${EVENT_COUNT}" -le 0 ]]; then
  echo "No events visible in cloud admin after outbox drain"
  exit 1
fi

echo "Cloud-down recovery smoke test passed"
