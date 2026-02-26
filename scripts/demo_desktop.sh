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

echo "[demo-desktop] starting desktop in demo mode"
echo "[demo-desktop] EDGE_ENV=${EDGE_ENV} ALLOW_FALLBACK_EMBEDDINGS=${ALLOW_FALLBACK_EMBEDDINGS} TELEMETRY_ENABLED=${TELEMETRY_ENABLED}"

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
npm run tauri:dev
