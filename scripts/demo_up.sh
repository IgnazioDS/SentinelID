#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CLOUD_URL="${CLOUD_URL:-http://127.0.0.1:8000}"
ADMIN_UI_URL="${ADMIN_UI_URL:-http://127.0.0.1:3000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_TOKEN:-dev-admin-token}}"
ADMIN_UI_USERNAME="${ADMIN_UI_USERNAME:-admin}"
ADMIN_UI_PASSWORD="${ADMIN_UI_PASSWORD:-admin123!}"
DEMO_FORCE_BUILD="${DEMO_FORCE_BUILD:-0}"
DEMO_HEALTH_TIMEOUT_SECONDS="${DEMO_HEALTH_TIMEOUT_SECONDS:-180}"

cd "${REPO_ROOT}"

echo "[demo-up] starting docker compose stack (postgres/cloud/admin)"
compose_args=(up -d postgres cloud admin)
if [[ "${DEMO_FORCE_BUILD}" == "1" ]]; then
  compose_args=(up -d --build postgres cloud admin)
fi

attempt=1
until docker compose "${compose_args[@]}"; do
  if [[ "${attempt}" -ge 3 ]]; then
    echo "[demo-up] docker compose failed after ${attempt} attempts"
    exit 1
  fi
  echo "[demo-up] docker compose failed (attempt ${attempt}); retrying..."
  attempt=$((attempt + 1))
  sleep 2
done

echo "[demo-up] waiting for cloud health"
for _ in $(seq 1 $((DEMO_HEALTH_TIMEOUT_SECONDS * 2))); do
  if curl -fsS "${CLOUD_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS "${CLOUD_URL}/health" >/dev/null 2>&1; then
  echo "Cloud health check failed: ${CLOUD_URL}/health"
  echo "[demo-up] docker compose ps"
  docker compose ps || true
  echo "[demo-up] cloud logs (tail 120)"
  docker compose logs --tail=120 cloud || true
  exit 1
fi

echo "[demo-up] waiting for admin ui"
for _ in $(seq 1 $((DEMO_HEALTH_TIMEOUT_SECONDS * 2))); do
  if curl -fsS "${ADMIN_UI_URL}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS "${ADMIN_UI_URL}" >/dev/null 2>&1; then
  echo "Admin UI health check failed: ${ADMIN_UI_URL}"
  echo "[demo-up] docker compose ps"
  docker compose ps || true
  echo "[demo-up] admin logs (tail 120)"
  docker compose logs --tail=120 admin || true
  exit 1
fi

echo "[demo-up] waiting for admin cloud proxy"
COOKIE_JAR="$(mktemp -t sentinelid_demo_admin_cookie.XXXXXX)"
cleanup_cookie() {
  rm -f "${COOKIE_JAR}" >/dev/null 2>&1 || true
}
trap cleanup_cookie EXIT
for _ in $(seq 1 $((DEMO_HEALTH_TIMEOUT_SECONDS * 2))); do
  if curl -fsS -c "${COOKIE_JAR}" \
      -H "Content-Type: application/json" \
      -X POST \
      -d "{\"username\":\"${ADMIN_UI_USERNAME}\",\"password\":\"${ADMIN_UI_PASSWORD}\"}" \
      "${ADMIN_UI_URL}/api/admin/session/login" >/dev/null 2>&1 \
    && curl -fsS -b "${COOKIE_JAR}" "${ADMIN_UI_URL}/api/cloud/v1/admin/stats?window=24h" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS -c "${COOKIE_JAR}" \
    -H "Content-Type: application/json" \
    -X POST \
    -d "{\"username\":\"${ADMIN_UI_USERNAME}\",\"password\":\"${ADMIN_UI_PASSWORD}\"}" \
    "${ADMIN_UI_URL}/api/admin/session/login" >/dev/null 2>&1 \
  || ! curl -fsS -b "${COOKIE_JAR}" "${ADMIN_UI_URL}/api/cloud/v1/admin/stats?window=24h" >/dev/null 2>&1; then
  echo "Admin proxy check failed: ${ADMIN_UI_URL}/api/cloud/v1/admin/stats?window=24h"
  echo "Direct cloud admin check:"
  curl -sS -H "X-Admin-Token: ${ADMIN_TOKEN}" "${CLOUD_URL}/v1/admin/stats?window=24h" || true
  exit 1
fi

echo "[demo-up] demo stack healthy"
