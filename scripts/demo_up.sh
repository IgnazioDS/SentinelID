#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CLOUD_URL="${CLOUD_URL:-http://127.0.0.1:8000}"
ADMIN_UI_URL="${ADMIN_UI_URL:-http://127.0.0.1:3000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_TOKEN:-dev-admin-token}}"

cd "${REPO_ROOT}"

echo "[demo-up] starting docker compose stack (postgres/cloud/admin)"
docker compose up -d --build postgres cloud admin

echo "[demo-up] waiting for cloud health"
for _ in $(seq 1 160); do
  if curl -fsS "${CLOUD_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS "${CLOUD_URL}/health" >/dev/null 2>&1; then
  echo "Cloud health check failed: ${CLOUD_URL}/health"
  exit 1
fi

echo "[demo-up] waiting for admin ui"
for _ in $(seq 1 160); do
  if curl -fsS "${ADMIN_UI_URL}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS "${ADMIN_UI_URL}" >/dev/null 2>&1; then
  echo "Admin UI health check failed: ${ADMIN_UI_URL}"
  exit 1
fi

echo "[demo-up] waiting for admin cloud proxy"
for _ in $(seq 1 160); do
  if curl -fsS "${ADMIN_UI_URL}/api/cloud/v1/admin/stats?window=24h" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS "${ADMIN_UI_URL}/api/cloud/v1/admin/stats?window=24h" >/dev/null 2>&1; then
  echo "Admin proxy check failed: ${ADMIN_UI_URL}/api/cloud/v1/admin/stats?window=24h"
  echo "Direct cloud admin check:"
  curl -sS -H "X-Admin-Token: ${ADMIN_TOKEN}" "${CLOUD_URL}/v1/admin/stats?window=24h" || true
  exit 1
fi

echo "[demo-up] demo stack healthy"
