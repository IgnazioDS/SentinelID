#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

: "${CLOUD_URL:=http://127.0.0.1:8000}"
: "${ADMIN_UI_URL:=http://127.0.0.1:3000}"
: "${EDGE_URL:=http://127.0.0.1:8787}"
: "${EDGE_TOKEN:=devtoken}"
: "${ADMIN_TOKEN:=${ADMIN_API_TOKEN:-dev-admin-token}}"
: "${ADMIN_UI_USERNAME:=admin}"
: "${ADMIN_UI_PASSWORD:=admin123!}"
: "${DEMO_FORCE_BUILD:=0}"
: "${DEMO_VERIFY_KEEP_STACK:=0}"
: "${DEMO_VERIFY_DESKTOP:=0}"
: "${DEMO_VERIFY_DESKTOP_AUTO_CLOSE_SECONDS:=20}"

cleanup() {
  if [[ "${DEMO_VERIFY_KEEP_STACK}" != "1" ]]; then
    "${REPO_ROOT}/scripts/demo_down.sh" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[demo-verify] demo-up"
DEMO_FORCE_BUILD="${DEMO_FORCE_BUILD}" \
  ADMIN_UI_USERNAME="${ADMIN_UI_USERNAME}" \
  ADMIN_UI_PASSWORD="${ADMIN_UI_PASSWORD}" \
  ADMIN_TOKEN="${ADMIN_TOKEN}" \
  "${REPO_ROOT}/scripts/demo_up.sh"

echo "[demo-verify] cloud smoke"
CLOUD_URL="${CLOUD_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" \
  "${REPO_ROOT}/scripts/smoke_test_cloud.sh"

echo "[demo-verify] recovery smoke"
CLOUD_URL="${CLOUD_URL}" EDGE_URL="${EDGE_URL}" EDGE_TOKEN="${EDGE_TOKEN}" ADMIN_TOKEN="${ADMIN_TOKEN}" \
  "${REPO_ROOT}/scripts/smoke_test_cloud_recovery.sh"

echo "[demo-verify] support bundle sanitization"
CLOUD_URL="${CLOUD_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" \
  "${REPO_ROOT}/scripts/check_support_bundle_sanitization.sh"

echo "[demo-verify] admin smoke"
API_URL="${CLOUD_URL}" ADMIN_UI_URL="${ADMIN_UI_URL}" ADMIN_TOKEN="${ADMIN_TOKEN}" \
  ADMIN_UI_USERNAME="${ADMIN_UI_USERNAME}" ADMIN_UI_PASSWORD="${ADMIN_UI_PASSWORD}" \
  "${REPO_ROOT}/scripts/smoke_test_admin.sh"

if [[ "${DEMO_VERIFY_DESKTOP}" == "1" ]]; then
  echo "[demo-verify] desktop launch/close semantics"
  DEMO_ALLOW_SIGINT_EXIT=1 \
    DEMO_AUTO_CLOSE_SECONDS="${DEMO_VERIFY_DESKTOP_AUTO_CLOSE_SECONDS}" \
    "${REPO_ROOT}/scripts/demo_desktop.sh"
fi

echo "[demo-verify] orphan check"
"${REPO_ROOT}/scripts/check_no_orphan_edge.sh"

echo "[demo-verify] completed successfully"
