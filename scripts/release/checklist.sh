#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

EDGE_URL="${EDGE_URL:-http://127.0.0.1:8787}"
EDGE_TOKEN="${EDGE_TOKEN:-${EDGE_AUTH_TOKEN:-devtoken}}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_TOKEN:-dev-admin-token}}"
ADMIN_UI_USERNAME="${ADMIN_UI_USERNAME:-admin}"
ADMIN_UI_PASSWORD="${ADMIN_UI_PASSWORD:-admin123!}"
CLOUD_URL="${CLOUD_URL:-http://127.0.0.1:8000}"
ADMIN_UI_URL="${ADMIN_UI_URL:-http://127.0.0.1:3000}"

PASSED_STEPS=()
FAILED_STEP=""
EDGE_PID=""
EDGE_LOG=""
SERVICES_STARTED=0
ORPHAN_BASELINE_PIDS="$(pgrep -f "run_edge.sh|sentinelid_edge.main:app" | tr '\n' ',' | sed 's/,$//' || true)"
DIAG_DIR="${RELEASE_CHECK_DIAG_DIR:-output/ci/logs}"

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
  pkill -f "sentinelid_edge.main:app --host 127.0.0.1 --port 8787" >/dev/null 2>&1 || true
  if [[ "${SERVICES_STARTED}" == "1" && "${KEEP_SERVICES:-0}" != "1" ]]; then
    docker compose down >/dev/null 2>&1 || true
  fi
}

dump_failure_diagnostics() {
  if [[ -z "${FAILED_STEP}" ]]; then
    return
  fi

  mkdir -p "${DIAG_DIR}"
  local ts
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  local prefix="${DIAG_DIR}/release_check_failure_${ts}"

  {
    echo "failed_step=${FAILED_STEP}"
    echo "cloud_url=${CLOUD_URL}"
    echo "admin_ui_url=${ADMIN_UI_URL}"
    echo "edge_url=${EDGE_URL}"
  } | tee "${prefix}_summary.txt"

  if [[ -n "${EDGE_LOG}" && -f "${EDGE_LOG}" ]]; then
    echo "[diag] writing edge log tail: ${prefix}_edge_tail.log"
    tail -n 200 "${EDGE_LOG}" | tee "${prefix}_edge_tail.log" >/dev/null
  fi

  echo "[diag] writing docker compose ps: ${prefix}_compose_ps.txt"
  docker compose ps > "${prefix}_compose_ps.txt" 2>&1 || true

  echo "[diag] writing docker compose logs: ${prefix}_compose.log"
  docker compose logs --no-color > "${prefix}_compose.log" 2>&1 || true
}

on_exit() {
  dump_failure_diagnostics
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
run_step "version consistency" ./scripts/release/check_version_consistency.sh
run_step "duplicate artifact guard" ./scripts/release/check_no_duplicate_pairs.sh
run_step "edge tests" make test-edge
run_step "cloud tests" make test-cloud
run_step "warning budget" ./scripts/ci/check_warning_budget.sh
run_step "tauri config validation" make check-tauri-config
run_step "desktop web build" make build-desktop-web
run_step "desktop cargo check" make check-desktop-rust
run_step "security: no admin token in client bundle" ./scripts/release/check_no_public_admin_token_bundle.sh
run_step "compose admin env wiring" bash -c '
  cfg="$(docker compose config)"
  echo "$cfg" | grep -q "CLOUD_BASE_URL: http://cloud:8000" || {
    echo "docker compose config missing CLOUD_BASE_URL=http://cloud:8000"
    exit 1
  }
  echo "$cfg" | grep -q "ADMIN_API_TOKEN:" || {
    echo "docker compose config missing ADMIN_API_TOKEN"
    exit 1
  }
  echo "$cfg" | grep -q "ADMIN_UI_USERNAME:" || {
    echo "docker compose config missing ADMIN_UI_USERNAME"
    exit 1
  }
  echo "$cfg" | grep -q "ADMIN_UI_PASSWORD_HASH:" || {
    echo "docker compose config missing ADMIN_UI_PASSWORD_HASH"
    exit 1
  }
  echo "$cfg" | grep -q "ADMIN_UI_SESSION_SECRET:" || {
    echo "docker compose config missing ADMIN_UI_SESSION_SECRET"
    exit 1
  }
  echo "$cfg" | grep -q "ADMIN_UI_SESSION_SECURE:" || {
    echo "docker compose config missing ADMIN_UI_SESSION_SECURE"
    exit 1
  }
'
run_step "security: no public admin token config" bash -c '
  if rg -n "NEXT_PUBLIC_ADMIN_TOKEN" .env.example docker-compose.yml >/dev/null 2>&1; then
    echo "NEXT_PUBLIC_ADMIN_TOKEN is still present in runtime config"
    exit 1
  fi
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
run_step "demo readiness: reliability SLO report" env CLOUD_URL="${CLOUD_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" OUT="output/ci/reliability_slo.json" ./scripts/ci/export_reliability_slo.py
run_step "demo readiness: cloud recovery smoke" env CLOUD_URL="${CLOUD_URL}" EDGE_TOKEN="${EDGE_TOKEN}" ADMIN_TOKEN="${ADMIN_TOKEN}" ./scripts/smoke_test_cloud_recovery.sh
run_step "demo readiness: support bundle sanitized" env CLOUD_URL="${CLOUD_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" ./scripts/check_support_bundle_sanitization.sh
run_step "demo readiness: support bundle artifact" env CLOUD_URL="${CLOUD_URL}" EDGE_URL="${EDGE_URL}" EDGE_TOKEN="${EDGE_TOKEN}" ADMIN_TOKEN="${ADMIN_TOKEN}" ./scripts/support_bundle.sh
run_step "admin smoke" env API_URL="${CLOUD_URL}" ADMIN_UI_URL="${ADMIN_UI_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" ADMIN_UI_USERNAME="${ADMIN_UI_USERNAME}" ADMIN_UI_PASSWORD="${ADMIN_UI_PASSWORD}" ./scripts/smoke_test_admin.sh
run_step "desktop smoke" ./scripts/smoke_test_desktop.sh
run_step "demo readiness: bundling smoke" ./scripts/smoke_test_bundling.sh
run_step "demo readiness: no orphan edge process" env ORPHAN_BASELINE_PIDS="${ORPHAN_BASELINE_PIDS}" ./scripts/check_no_orphan_edge.sh
run_step "release evidence pack" ./scripts/release/build_evidence_pack.sh

FAILED_STEP=""
