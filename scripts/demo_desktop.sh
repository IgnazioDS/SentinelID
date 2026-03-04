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
: "${VITE_ADMIN_UI_URL:=http://127.0.0.1:3000/support}"
: "${DEMO_ALLOW_SIGINT_EXIT:=1}"
: "${DEMO_ALLOW_SIGTERM_EXIT:=1}"
: "${DEMO_AUTO_CLOSE_SECONDS:=0}"

ORPHAN_BASELINE_PIDS="$(pgrep -f "run_edge.sh|sentinelid_edge.main:app" | tr '\n' ',' | sed 's/,$//' || true)"
desktop_pid=""

pid_in_baseline() {
  local pid="$1"
  [[ -n "${ORPHAN_BASELINE_PIDS}" && ",${ORPHAN_BASELINE_PIDS}," == *",${pid},"* ]]
}

list_descendants() {
  local pid="$1"
  local child
  for child in $(pgrep -P "${pid}" 2>/dev/null || true); do
    echo "${child}"
    list_descendants "${child}"
  done
}

signal_process_tree() {
  local root_pid="$1"
  local signal="$2"
  local pids
  pids="$(
    {
      list_descendants "${root_pid}"
      echo "${root_pid}"
    } | awk 'NF' | sort -n -u
  )"
  [[ -z "${pids}" ]] && return 0

  local pid
  for pid in ${pids}; do
    kill -"${signal}" "${pid}" >/dev/null 2>&1 || true
  done
}

wait_for_exit() {
  local pid="$1"
  local timeout_seconds="$2"
  local elapsed=0
  while kill -0 "${pid}" >/dev/null 2>&1; do
    if [[ "${elapsed}" -ge "${timeout_seconds}" ]]; then
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  return 0
}

terminate_desktop_tree() {
  [[ -z "${desktop_pid}" ]] && return 0
  if ! kill -0 "${desktop_pid}" >/dev/null 2>&1; then
    return 0
  fi

  signal_process_tree "${desktop_pid}" "INT"
  if wait_for_exit "${desktop_pid}" 6; then
    return 0
  fi

  signal_process_tree "${desktop_pid}" "TERM"
  if wait_for_exit "${desktop_pid}" 6; then
    return 0
  fi

  signal_process_tree "${desktop_pid}" "KILL"
  wait_for_exit "${desktop_pid}" 3 || true
}

cleanup_new_edge_processes() {
  local matches
  matches="$(pgrep -f "run_edge.sh|sentinelid_edge.main:app" || true)"
  [[ -z "${matches}" ]] && return 0

  local pid
  for pid in ${matches}; do
    if pid_in_baseline "${pid}"; then
      continue
    fi
    kill "${pid}" >/dev/null 2>&1 || true
    wait "${pid}" >/dev/null 2>&1 || true
  done
}

on_exit() {
  terminate_desktop_tree
  cleanup_new_edge_processes
}

trap on_exit EXIT

echo "[demo-desktop] starting desktop in demo mode"
echo "[demo-desktop] EDGE_ENV=${EDGE_ENV} ALLOW_FALLBACK_EMBEDDINGS=${ALLOW_FALLBACK_EMBEDDINGS} TELEMETRY_ENABLED=${TELEMETRY_ENABLED}"
echo "[demo-desktop] close behavior: expected exits include 0 and optional interrupt exits (130/143)"
echo "[demo-desktop] auto-close timeout: ${DEMO_AUTO_CLOSE_SECONDS}s (0 disables timeout mode)"

make check-tauri-config

export EDGE_ENV
export ALLOW_FALLBACK_EMBEDDINGS
export TELEMETRY_ENABLED
export CLOUD_INGEST_URL
export ADMIN_API_TOKEN
export VITE_DEMO_MODE
export VITE_CLOUD_BASE_URL
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
      echo "[demo-desktop] timeout reached after ${DEMO_AUTO_CLOSE_SECONDS}s; initiating shutdown"
      terminate_desktop_tree
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
