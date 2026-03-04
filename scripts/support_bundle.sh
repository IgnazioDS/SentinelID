#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${REPO_ROOT}/scripts/support/out"
TMP_DIR="$(mktemp -d -t sentinelid_support_bundle.XXXXXX)"

EDGE_URL="${EDGE_URL:-http://127.0.0.1:8787}"
EDGE_TOKEN="${EDGE_TOKEN:-${EDGE_AUTH_TOKEN:-}}"
CLOUD_URL="${CLOUD_URL:-http://127.0.0.1:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_TOKEN:-}}"
EVENT_LIMIT="${SUPPORT_EVENTS_LIMIT:-50}"

mkdir -p "${OUT_DIR}"

cleanup() {
  rm -rf "${TMP_DIR}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sanitize_json() {
  local input_path="$1"
  local output_path="$2"
  python3 - "${input_path}" "${output_path}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

in_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])

forbidden = {
    "authorization",
    "token",
    "admin_token",
    "edge_auth_token",
    "signature",
    "batch_signature",
    "device_public_key",
    "frame",
    "frames",
    "image",
    "images",
    "embedding",
    "embeddings",
}


def sanitize(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lower = str(key).lower()
            if lower in forbidden or "token" in lower or "signature" in lower:
                out[key] = "[REDACTED]"
            else:
                out[key] = sanitize(item)
        return out
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str) and value.lower().startswith("bearer "):
        return "Bearer [REDACTED]"
    return value

raw = json.loads(in_path.read_text())
out_path.write_text(json.dumps(sanitize(raw), indent=2, sort_keys=True))
PY
}

record_request_id() {
  local headers_path="$1"
  local label="$2"
  local rid
  rid="$(tr -d '\r' <"${headers_path}" | awk 'tolower($1)=="x-request-id:"{print $2}' | tail -n 1)"
  if [[ -n "${rid}" ]]; then
    echo "${label}: ${rid}" >> "${TMP_DIR}/request_ids.txt"
  fi
}

write_status_json() {
  local output_path="$1"
  local status="$2"
  local detail="${3:-}"

  python3 - "${output_path}" "${status}" "${detail}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

out_path = Path(sys.argv[1])
status = sys.argv[2]
detail = sys.argv[3]

payload = {"status": status}
if detail:
    payload["detail"] = detail

out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
PY
}

fetch_json() {
  local label="$1"
  local url="$2"
  local output_base="$3"
  local auth_header="${4:-}"

  local headers_path="${TMP_DIR}/${output_base}.headers"
  local raw_path="${TMP_DIR}/${output_base}.raw.json"
  local clean_path="${TMP_DIR}/${output_base}.json"
  local err_path="${TMP_DIR}/${output_base}.err.log"

  local curl_args=("-sS" "-f" "-D" "${headers_path}" "${url}")
  if [[ -n "${auth_header}" ]]; then
    curl_args=("-sS" "-f" "-D" "${headers_path}" "-H" "${auth_header}" "${url}")
  fi

  if ! curl "${curl_args[@]}" >"${raw_path}" 2>"${err_path}"; then
    local err_detail="request failed"
    if [[ -s "${err_path}" ]]; then
      err_detail="$(head -n 1 "${err_path}")"
    fi
    write_status_json "${clean_path}" "unavailable" "${err_detail}"
    rm -f "${headers_path}" "${raw_path}" "${err_path}" >/dev/null 2>&1 || true
    return
  fi

  sanitize_json "${raw_path}" "${clean_path}"
  record_request_id "${headers_path}" "${label}"
  rm -f "${headers_path}" "${raw_path}" "${err_path}" >/dev/null 2>&1 || true
}

# Collect API snapshots
if [[ -n "${EDGE_TOKEN}" ]]; then
  fetch_json "edge_diagnostics" "${EDGE_URL}/api/v1/diagnostics" "edge_diagnostics" "Authorization: Bearer ${EDGE_TOKEN}"
else
  write_status_json "${TMP_DIR}/edge_diagnostics.json" "skipped" "EDGE_TOKEN missing"
fi

if [[ -n "${ADMIN_TOKEN}" ]]; then
  fetch_json "cloud_stats" "${CLOUD_URL}/v1/admin/stats" "cloud_stats" "X-Admin-Token: ${ADMIN_TOKEN}"
  fetch_json "cloud_events" "${CLOUD_URL}/v1/admin/events?limit=${EVENT_LIMIT}" "cloud_events" "X-Admin-Token: ${ADMIN_TOKEN}"
else
  write_status_json "${TMP_DIR}/cloud_stats.json" "skipped" "ADMIN_TOKEN missing"
  write_status_json "${TMP_DIR}/cloud_events.json" "skipped" "ADMIN_TOKEN missing"
fi

# Local audit/outbox summary (sanitized, no raw event payloads)
python3 - "${REPO_ROOT}" "${TMP_DIR}/audit_summary.json" <<'PY'
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
out_path = Path(sys.argv[2])
db_path = os.environ.get("SENTINELID_DB_PATH", str(repo_root / "apps" / "edge" / ".sentinelid" / "audit.db"))
summary = {
    "db_path": db_path,
    "audit_event_count": 0,
    "outbox_counts": {},
    "audit_hash_tips": [],
    "status": "ok",
}

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM audit_events")
    summary["audit_event_count"] = int(cur.fetchone()["c"])

    cur.execute("SELECT status, COUNT(*) AS c FROM outbox_events GROUP BY status")
    summary["outbox_counts"] = {row["status"]: int(row["c"]) for row in cur.fetchall()}

    cur.execute(
        """
        SELECT timestamp, outcome, hash, prev_hash, request_id, session_id
        FROM audit_events
        ORDER BY id DESC
        LIMIT 20
        """
    )
    summary["audit_hash_tips"] = [
        {
            "timestamp": int(row["timestamp"]),
            "outcome": row["outcome"],
            "hash": row["hash"],
            "prev_hash": row["prev_hash"],
            "request_id": row["request_id"],
            "session_id": row["session_id"],
        }
        for row in cur.fetchall()
    ]
    conn.close()
except Exception as exc:
    summary["status"] = "error"
    summary["error"] = str(exc)

out_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
PY

# Environment and version summary
{
  echo "generated_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev=$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "git_branch=$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "edge_url=${EDGE_URL}"
  echo "cloud_url=${CLOUD_URL}"
  echo "python_version=$(python3 --version 2>/dev/null || echo unavailable)"
  echo "node_version=$(node --version 2>/dev/null || echo unavailable)"
  echo "cargo_version=$(cargo --version 2>/dev/null || echo unavailable)"
  echo "docker_compose_version=$(docker compose version 2>/dev/null | head -n1 || echo unavailable)"
} > "${TMP_DIR}/env_summary.txt"

if [[ ! -f "${TMP_DIR}/request_ids.txt" ]]; then
  echo "no_request_ids_collected" > "${TMP_DIR}/request_ids.txt"
fi

BUNDLE_TS="$(date -u +%Y%m%dT%H%M%SZ)"
BUNDLE_PATH="${OUT_DIR}/support_bundle_${BUNDLE_TS}.tar.gz"

COPYFILE_DISABLE=1 tar -czf "${BUNDLE_PATH}" -C "${TMP_DIR}" .

echo "Support bundle created: ${BUNDLE_PATH}"
