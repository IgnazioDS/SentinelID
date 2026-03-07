#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DESKTOP_APP="${PROJECT_ROOT}/apps/desktop"
RESOURCES_DIR="${DESKTOP_APP}/resources/edge"
ACTIVE_VENV_DIR="${RESOURCES_DIR}/pyvenv_active"
LEGACY_VENV_DIR="${RESOURCES_DIR}/pyvenv"
RUNNER="${RESOURCES_DIR}/run_edge.sh"
SKIP_DESKTOP_BUILD="${SKIP_DESKTOP_BUILD:-0}"
SKIP_BUNDLE="${SKIP_BUNDLE:-0}"
HEALTH_TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-120}"

PORT="$(
  python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"
TOKEN="bundling-smoke-token"
BASE_URL="http://127.0.0.1:${PORT}"
EDGE_LOG="$(mktemp -t sentinelid_bundle_smoke_edge.XXXXXX.log)"
EDGE_PID=""

echo "Bundling smoke config: skip_bundle=${SKIP_BUNDLE} skip_desktop_build=${SKIP_DESKTOP_BUILD} health_timeout_sec=${HEALTH_TIMEOUT_SEC}"

cleanup() {
  if [[ -n "${EDGE_PID}" ]] && kill -0 "${EDGE_PID}" >/dev/null 2>&1; then
    kill "${EDGE_PID}" >/dev/null 2>&1 || true
    wait "${EDGE_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ "${SKIP_BUNDLE}" != "1" ]]; then
  echo "Bundling smoke: bundle edge runtime"
  "${PROJECT_ROOT}/scripts/bundle_edge_venv.sh"
fi

if [[ "${SKIP_DESKTOP_BUILD}" != "1" ]]; then
  echo "Bundling smoke: build desktop bundle"
  make -C "${PROJECT_ROOT}" build-desktop
fi

if [[ ! -x "${RUNNER}" ]]; then
  echo "Bundled runner missing or not executable: ${RUNNER}"
  exit 1
fi

if [[ -x "${ACTIVE_VENV_DIR}/bin/python" ]]; then
  VENV_DIR="${ACTIVE_VENV_DIR}"
else
  VENV_DIR="${LEGACY_VENV_DIR}"
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Bundled python missing: ${ACTIVE_VENV_DIR}/bin/python (or legacy ${LEGACY_VENV_DIR}/bin/python)"
  exit 1
fi

for pkg in fastapi uvicorn pydantic sqlalchemy; do
  if ! "${VENV_DIR}/bin/python" -m pip show "${pkg}" >/dev/null 2>&1; then
    echo "Required package ${pkg} missing in bundled venv"
    exit 1
  fi
done

echo "Bundling smoke: start bundled runner on dynamic port ${PORT}"
# Bundling smoke is a controlled debugging path, so opt into keychain fallback
# explicitly when the runner has no OS keyring service.
ALLOW_KEYCHAIN_FALLBACK="1" EDGE_PORT="${PORT}" EDGE_AUTH_TOKEN="${TOKEN}" EDGE_ENV="prod" \
  "${RUNNER}" >"${EDGE_LOG}" 2>&1 &
EDGE_PID=$!

MAX_POLLS=$((HEALTH_TIMEOUT_SEC * 2))
for _ in $(seq 1 "${MAX_POLLS}"); do
  if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${EDGE_PID}" >/dev/null 2>&1; then
    echo "Bundled edge process exited before becoming healthy"
    tail -n 120 "${EDGE_LOG}" || true
    exit 1
  fi
  sleep 0.5
done

if ! curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
  echo "Bundled edge failed health check at ${BASE_URL}/health within ${HEALTH_TIMEOUT_SEC}s"
  tail -n 120 "${EDGE_LOG}" || true
  exit 1
fi

if ! curl -fsS "${BASE_URL}/api/v1/health" >/dev/null 2>&1; then
  echo "Bundled edge failed API health check at ${BASE_URL}/api/v1/health"
  tail -n 120 "${EDGE_LOG}" || true
  exit 1
fi

AUTH_STATUS="$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/settings/telemetry")"
if [[ "${AUTH_STATUS}" != "401" ]]; then
  echo "Expected auth-gated endpoint to return 401, got ${AUTH_STATUS}"
  tail -n 120 "${EDGE_LOG}" || true
  exit 1
fi

echo "Bundling smoke test passed"
