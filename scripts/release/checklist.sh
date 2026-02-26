#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

EDGE_URL="${EDGE_URL:-http://127.0.0.1:8787}"
EDGE_TOKEN="${EDGE_TOKEN:-${EDGE_AUTH_TOKEN:-devtoken}}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_TOKEN:-dev-admin-token}}"
CLOUD_URL="${CLOUD_URL:-http://127.0.0.1:8000}"
ADMIN_UI_URL="${ADMIN_UI_URL:-http://127.0.0.1:3000}"

PASSED_STEPS=()
FAILED_STEP=""
EDGE_PID=""
SERVICES_STARTED=0

summary() {
  echo ""
  if [[ -n "${FAILED_STEP}" ]]; then
    echo "Release checklist failed at step: ${FAILED_STEP}"
    echo "Passed steps: ${#PASSED_STEPS[@]}"
    for step in "${PASSED_STEPS[@]}"; do
      echo "  - ${step}"
    done
  else
    echo "Release checklist completed successfully"
    echo "Passed steps: ${#PASSED_STEPS[@]}"
    for step in "${PASSED_STEPS[@]}"; do
      echo "  - ${step}"
    done
  fi
}

cleanup() {
  if [[ -n "${EDGE_PID}" ]] && kill -0 "${EDGE_PID}" >/dev/null 2>&1; then
    kill "${EDGE_PID}" >/dev/null 2>&1 || true
    wait "${EDGE_PID}" >/dev/null 2>&1 || true
  fi
  if [[ "${SERVICES_STARTED}" == "1" && "${KEEP_SERVICES:-0}" != "1" ]]; then
    docker compose down >/dev/null 2>&1 || true
  fi
}

on_exit() {
  cleanup
  summary
}

trap on_exit EXIT

run_step() {
  local name="$1"
  shift
  echo "[run] ${name}"
  if "$@"; then
    PASSED_STEPS+=("${name}")
  else
    FAILED_STEP="${name}"
    return 1
  fi
}

run_step "edge preflight imports" make check-edge-preflight
run_step "edge tests" make test-edge
run_step "cloud tests" make test-cloud
run_step "tauri config validation" make check-tauri-config
run_step "desktop web build" make build-desktop-web
run_step "desktop cargo check" make check-desktop-rust
run_step "compose admin env wiring" bash -c '
  cfg="$(docker compose config)"
  echo "$cfg" | grep -q "NEXT_PUBLIC_CLOUD_BASE_URL: http://cloud:8000" || {
    echo "docker compose config missing NEXT_PUBLIC_CLOUD_BASE_URL=http://cloud:8000"
    exit 1
  }
  echo "$cfg" | grep -q "NEXT_PUBLIC_ADMIN_TOKEN:" || {
    echo "docker compose config missing NEXT_PUBLIC_ADMIN_TOKEN"
    exit 1
  }
'
run_step "docker build (cloud/admin)" make docker-build

EDGE_LOG="$(mktemp -t sentinelid_release_edge.XXXXXX.log)"
echo "[run] start edge for smoke/perf"
(
  cd apps/edge
  if command -v poetry >/dev/null 2>&1; then
    EDGE_ENV=dev ALLOW_FALLBACK_EMBEDDINGS=1 EDGE_AUTH_TOKEN="${EDGE_TOKEN}" poetry run uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 8787 >"${EDGE_LOG}" 2>&1
  elif [[ -x .venv/bin/poetry ]]; then
    EDGE_ENV=dev ALLOW_FALLBACK_EMBEDDINGS=1 EDGE_AUTH_TOKEN="${EDGE_TOKEN}" .venv/bin/poetry run uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 8787 >"${EDGE_LOG}" 2>&1
  else
    echo "Poetry not found for edge runtime"
    exit 1
  fi
) &
EDGE_PID=$!

for _ in $(seq 1 80); do
  if curl -fsS "${EDGE_URL}/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS "${EDGE_URL}/api/v1/health" >/dev/null 2>&1; then
  FAILED_STEP="start edge for smoke/perf"
  echo "Edge failed to start; tailing logs"
  tail -n 120 "${EDGE_LOG}" || true
  exit 1
fi
PASSED_STEPS+=("start edge for smoke/perf")

run_step "edge smoke" env EDGE_URL="${EDGE_URL}" EDGE_TOKEN="${EDGE_TOKEN}" ./scripts/smoke_test_edge.sh
run_step "edge perf" env EDGE_URL="${EDGE_URL}" EDGE_TOKEN="${EDGE_TOKEN}" make perf-edge

cleanup
EDGE_PID=""

echo "[section] demo readiness"
run_step "demo readiness: demo-up" make demo-up
SERVICES_STARTED=1

run_step "cloud smoke" env CLOUD_URL="${CLOUD_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" ./scripts/smoke_test_cloud.sh
run_step "demo readiness: cloud recovery smoke" env CLOUD_URL="${CLOUD_URL}" EDGE_URL="${EDGE_URL}" EDGE_TOKEN="${EDGE_TOKEN}" ADMIN_TOKEN="${ADMIN_TOKEN}" ./scripts/smoke_test_cloud_recovery.sh
run_step "demo readiness: support bundle sanitized" env CLOUD_URL="${CLOUD_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" bash -c '
  tmp_bundle="$(mktemp -t sentinelid_release_bundle.XXXXXX.tar.gz)"
  trap "rm -f \"$tmp_bundle\"" EXIT
  curl -fsS -H "X-Admin-Token: ${ADMIN_TOKEN}" -X POST \
    "${CLOUD_URL}/v1/admin/support-bundle?window=24h&events_limit=50" \
    -o "$tmp_bundle"
  python3 - "$tmp_bundle" <<'"'"'PY'"'"'
from __future__ import annotations

import json
import tarfile
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists() or path.stat().st_size == 0:
    raise SystemExit("support bundle download is empty")

forbidden_fragments = ("token", "signature", "embedding", "frame", "image")
allowed_redacted = {"[REDACTED]", "", None}
value_violations = []

def inspect(value, ctx: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lower = str(key).lower()
            if any(fragment in lower for fragment in forbidden_fragments):
                if isinstance(child, (dict, list)) and child not in ({}, []):
                    value_violations.append(f"{ctx}.{key} non-empty structured sensitive field")
                elif child not in allowed_redacted:
                    value_violations.append(f"{ctx}.{key}={child!r}")
            inspect(child, f"{ctx}.{key}")
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            inspect(child, f"{ctx}[{idx}]")
    elif isinstance(value, str):
        lower = value.lower()
        if lower.startswith("bearer ") and value != "Bearer [REDACTED]":
            value_violations.append(f"{ctx} has non-redacted bearer token")
        if lower.startswith("data:image/"):
            value_violations.append(f"{ctx} has raw image data")

json_count = 0
with tarfile.open(path, mode="r:gz") as archive:
    members = [member for member in archive.getmembers() if member.isfile()]
    if not members:
        raise SystemExit("support bundle has no files")
    for member in members:
        if not member.name.endswith(".json"):
            continue
        payload = archive.extractfile(member)
        if payload is None:
            continue
        data = json.loads(payload.read().decode("utf-8"))
        inspect(data, member.name)
        json_count += 1

if json_count == 0:
    raise SystemExit("support bundle missing json payloads")
if value_violations:
    raise SystemExit("support bundle sanitization violations: " + "; ".join(value_violations[:8]))
print("support bundle sanitization check passed")
PY
'
run_step "admin smoke" env API_URL="${CLOUD_URL}" ADMIN_UI_URL="${ADMIN_UI_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" ./scripts/smoke_test_admin.sh
run_step "desktop smoke" ./scripts/smoke_test_desktop.sh
run_step "demo readiness: bundling smoke" ./scripts/smoke_test_bundling.sh
run_step "demo readiness: no orphan edge process" ./scripts/check_no_orphan_edge.sh

FAILED_STEP=""
