#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

EDGE_URL="${EDGE_URL:-http://127.0.0.1:8787}"
EDGE_TOKEN="${EDGE_TOKEN:-devtoken}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_TOKEN:-dev-admin-token}}"
CLOUD_URL="${CLOUD_URL:-http://127.0.0.1:8000}"

if command -v poetry >/dev/null 2>&1; then
  EDGE_POETRY_CMD=(poetry)
elif [[ -x "${ROOT_DIR}/apps/edge/.venv/bin/poetry" ]]; then
  EDGE_POETRY_CMD=("${ROOT_DIR}/apps/edge/.venv/bin/poetry")
else
  echo "Poetry not found. Install Poetry or ensure apps/edge/.venv/bin/poetry exists."
  exit 1
fi

echo "[1/7] Running edge tests"
make test-edge

echo "[2/7] Running cloud tests"
make test-cloud

echo "[3/7] Running desktop build checks"
make build-desktop-web
make check-desktop-rust

echo "[4/7] Building cloud/admin Docker images"
make docker-build

echo "[5/7] Running edge smoke + perf"
EDGE_LOG="$(mktemp -t sentinelid_release_edge.XXXXXX.log)"
(
  cd apps/edge
  "${EDGE_POETRY_CMD[@]}" run uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 8787 >"${EDGE_LOG}" 2>&1
) &
EDGE_PID=$!

cleanup() {
  if kill -0 "${EDGE_PID}" >/dev/null 2>&1; then
    kill "${EDGE_PID}" >/dev/null 2>&1 || true
    wait "${EDGE_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -fsS "${EDGE_URL}/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS "${EDGE_URL}/api/v1/health" >/dev/null 2>&1; then
  echo "Edge failed to start"
  tail -n 100 "${EDGE_LOG}" || true
  exit 1
fi

EDGE_URL="${EDGE_URL}" EDGE_TOKEN="${EDGE_TOKEN}" ./scripts/smoke_test_edge.sh

BENCH_OUT="scripts/eval/out/bench_edge_release_$(date +%Y%m%d_%H%M%S).json"
python3 scripts/perf/bench_edge.py --base-url "${EDGE_URL}" --token "${EDGE_TOKEN}" --attempts 5 --frames 10 --out "${BENCH_OUT}"
echo "Benchmark output: ${BENCH_OUT}"

cleanup
trap - EXIT

echo "[6/7] Starting cloud/admin services for smoke"
docker compose up -d postgres cloud admin >/dev/null

echo "[7/7] Running cloud/admin/desktop smoke scripts"
CLOUD_URL="${CLOUD_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" ./scripts/smoke_test_cloud.sh
./scripts/smoke_test_admin.sh
./scripts/smoke_test_desktop.sh
./scripts/smoke_test_bundling.sh

if [[ "${KEEP_SERVICES:-0}" != "1" ]]; then
  docker compose down >/dev/null
fi

echo "Release checklist completed successfully"
