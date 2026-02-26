#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

echo "Checking deprecation warning budget patterns..."

if rg -n "datetime\\.utcnow\\(|utcfromtimestamp\\(" apps/edge apps/cloud --glob '!**/poetry.lock' --glob '!**/.venv/**'; then
  echo "Found deprecated datetime usage that should be removed."
  exit 1
fi

if rg -n "class Config:" apps/edge apps/cloud --glob '!**/poetry.lock' --glob '!**/.venv/**'; then
  echo "Found legacy Pydantic class Config usage; use ConfigDict/SettingsConfigDict."
  exit 1
fi

echo "Warning budget check passed."
