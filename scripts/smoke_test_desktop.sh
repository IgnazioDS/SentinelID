#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCHER="${REPO_ROOT}/apps/desktop/resources/edge/run_edge.sh"

if [[ ! -x "${LAUNCHER}" ]]; then
  echo "Bundled launcher not found. Building bundle runtime first..."
  "${REPO_ROOT}/scripts/bundle_edge_venv.sh"
fi

PORT="${EDGE_PORT:-8891}"
HOST="${EDGE_HOST:-127.0.0.1}"
TOKEN="${EDGE_TOKEN:-${EDGE_AUTH_TOKEN:-desktop-smoke-token}}"
BASE_URL="http://${HOST}:${PORT}"
LOG_FILE="$(mktemp -t sentinelid_desktop_smoke.XXXXXX.log)"

if [[ -z "${TOKEN}" ]]; then
  echo "EDGE_TOKEN (or EDGE_AUTH_TOKEN) is required"
  exit 1
fi

echo "Starting bundled edge launcher: ${LAUNCHER}"
EDGE_PORT="${PORT}" EDGE_AUTH_TOKEN="${TOKEN}" EDGE_ENV="prod" \
  "${LAUNCHER}" >"${LOG_FILE}" 2>&1 &
EDGE_PID=$!

cleanup() {
  if kill -0 "${EDGE_PID}" 2>/dev/null; then
    kill "${EDGE_PID}" 2>/dev/null || true
    wait "${EDGE_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 80); do
  if curl -fsS "${BASE_URL}/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS "${BASE_URL}/api/v1/health" >/dev/null 2>&1; then
  echo "Bundled edge failed to start. Logs:"
  tail -n 120 "${LOG_FILE}" || true
  exit 1
fi

EDGE_URL="${BASE_URL}" EDGE_TOKEN="${TOKEN}" "${REPO_ROOT}/scripts/smoke_test_edge.sh"
echo "Desktop launcher smoke test passed"
