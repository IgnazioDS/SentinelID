#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

: "${EDGE_ENV:=dev}"
: "${ALLOW_FALLBACK_EMBEDDINGS:=0}"
: "${TELEMETRY_ENABLED:=1}"
: "${CLOUD_INGEST_URL:=http://127.0.0.1:8000/v1/ingest/events}"
: "${ADMIN_API_TOKEN:=dev-admin-token}"
: "${VITE_DEMO_MODE:=1}"
: "${VITE_CLOUD_BASE_URL:=http://127.0.0.1:8000}"
: "${VITE_ADMIN_TOKEN:=${ADMIN_API_TOKEN}}"
: "${VITE_ADMIN_UI_URL:=http://127.0.0.1:3000/support}"
: "${DEMO_ALLOW_SIGINT_EXIT:=1}"
: "${DEMO_ALLOW_SIGTERM_EXIT:=1}"
: "${DEMO_AUTO_CLOSE_SECONDS:=0}"

echo "[demo-desktop] starting desktop in demo mode"
echo "[demo-desktop] EDGE_ENV=${EDGE_ENV} ALLOW_FALLBACK_EMBEDDINGS=${ALLOW_FALLBACK_EMBEDDINGS} TELEMETRY_ENABLED=${TELEMETRY_ENABLED}"
echo "[demo-desktop] close behavior: expected exits include 0 and optional interrupt exits (130/143)"
echo "[demo-desktop] auto-close timeout: ${DEMO_AUTO_CLOSE_SECONDS}s (0 disables timeout mode)"

make check-tauri-config

export EDGE_ENV
export ALLOW_FALLBACK_EMBEDDINGS
export TELEMETRY_ENABLED
export CLOUD_INGEST_URL
export VITE_DEMO_MODE
export VITE_CLOUD_BASE_URL
export VITE_ADMIN_TOKEN
export VITE_ADMIN_UI_URL

cd apps/desktop
set +e
if [[ ! "${DEMO_AUTO_CLOSE_SECONDS}" =~ ^[0-9]+$ ]]; then
  echo "[demo-desktop] DEMO_AUTO_CLOSE_SECONDS must be a non-negative integer"
  exit 1
fi

if [[ "${DEMO_AUTO_CLOSE_SECONDS}" -gt 0 ]]; then
  npm run tauri:dev &
  desktop_pid=$!
  elapsed=0
  while kill -0 "${desktop_pid}" >/dev/null 2>&1; do
    if [[ "${elapsed}" -ge "${DEMO_AUTO_CLOSE_SECONDS}" ]]; then
      echo "[demo-desktop] timeout reached after ${DEMO_AUTO_CLOSE_SECONDS}s; sending SIGINT"
      kill -INT "${desktop_pid}" >/dev/null 2>&1 || true
      break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  wait "${desktop_pid}"
  status=$?
else
  npm run tauri:dev
  status=$?
fi
set -e

expected_exit=0
if [[ "${status}" -eq 0 ]]; then
  expected_exit=1
fi
if [[ "${status}" -eq 130 && "${DEMO_ALLOW_SIGINT_EXIT}" == "1" ]]; then
  expected_exit=1
fi
if [[ "${status}" -eq 143 && "${DEMO_ALLOW_SIGTERM_EXIT}" == "1" ]]; then
  expected_exit=1
fi

if [[ "${expected_exit}" -eq 1 ]]; then
  echo "[demo-desktop] completed with expected close status: ${status}"
  exit 0
fi

echo "[demo-desktop] unexpected close status: ${status}"
exit "${status}"
