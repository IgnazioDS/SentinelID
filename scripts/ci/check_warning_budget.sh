#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

echo "Checking deprecation warning budget patterns..."

if command -v rg >/dev/null 2>&1; then
  SEARCH_TOOL="rg"
else
  SEARCH_TOOL="grep"
fi

if [[ "${SEARCH_TOOL}" == "rg" ]]; then
  if rg -n "datetime\\.utcnow\\(|utcfromtimestamp\\(" apps/edge apps/cloud --glob '!**/poetry.lock' --glob '!**/.venv/**'; then
    echo "Found deprecated datetime usage that should be removed."
    exit 1
  fi

  if rg -n "class Config:" apps/edge apps/cloud --glob '!**/poetry.lock' --glob '!**/.venv/**'; then
    echo "Found legacy Pydantic class Config usage; use ConfigDict/SettingsConfigDict."
    exit 1
  fi
else
  if grep -RInE "datetime\\.utcnow\\(|utcfromtimestamp\\(" apps/edge apps/cloud --exclude-dir=.venv --exclude=poetry.lock; then
    echo "Found deprecated datetime usage that should be removed."
    exit 1
  fi

  if grep -RIn "class Config:" apps/edge apps/cloud --exclude-dir=.venv --exclude=poetry.lock; then
    echo "Found legacy Pydantic class Config usage; use ConfigDict/SettingsConfigDict."
    exit 1
  fi
fi

echo "Warning budget check passed."
