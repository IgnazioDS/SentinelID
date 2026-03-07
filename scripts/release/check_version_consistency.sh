#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

extract_or_fail() {
  local label="$1"
  local value="$2"
  if [[ -z "${value}" ]]; then
    echo "Unable to extract version from ${label}"
    exit 1
  fi
  echo "${value}"
}

extract_json_version_or_fail() {
  local label="$1"
  local path="$2"
  local value
  value="$(python3 - "${path}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    payload = json.load(f)
version = payload.get("package", {}).get("version", "")
print(version if isinstance(version, str) else "")
PY
)"
  extract_or_fail "${label}" "${value}"
}

CHANGELOG_VERSION="$(extract_or_fail "CHANGELOG.md" "$(sed -nE 's/^## v([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' CHANGELOG.md | head -n 1)")"
RUNBOOK_VERSION="$(extract_or_fail "RUNBOOK.md" "$(sed -nE 's/^# SentinelID Runbook \(v([0-9]+\.[0-9]+\.[0-9]+)\).*/\1/p' RUNBOOK.md | head -n 1)")"
RELEASE_GUIDE_VERSION="$(extract_or_fail "docs/RELEASE.md" "$(sed -nE 's/^# Release Guide \(v([0-9]+\.[0-9]+\.[0-9]+)\).*/\1/p' docs/RELEASE.md | head -n 1)")"
DEMO_CHECKLIST_VERSION="$(extract_or_fail "docs/DEMO_CHECKLIST.md" "$(sed -nE 's/^# SentinelID Demo Checklist \(v([0-9]+\.[0-9]+\.[0-9]+)\).*/\1/p' docs/DEMO_CHECKLIST.md | head -n 1)")"
MAKE_HELP_VERSION="$(extract_or_fail "Makefile help banner" "$(sed -nE 's/.*SentinelID v([0-9]+\.[0-9]+\.[0-9]+) Commands.*/\1/p' Makefile | head -n 1)")"
TAURI_PACKAGE_VERSION="$(extract_json_version_or_fail "apps/desktop/src-tauri/tauri.conf.json" "apps/desktop/src-tauri/tauri.conf.json")"

echo "Detected versions:"
echo "  changelog=${CHANGELOG_VERSION}"
echo "  runbook=${RUNBOOK_VERSION}"
echo "  release_guide=${RELEASE_GUIDE_VERSION}"
echo "  demo_checklist=${DEMO_CHECKLIST_VERSION}"
echo "  make_help=${MAKE_HELP_VERSION}"
echo "  tauri_package=${TAURI_PACKAGE_VERSION}"

if [[ "${CHANGELOG_VERSION}" != "${RUNBOOK_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${RELEASE_GUIDE_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${DEMO_CHECKLIST_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${MAKE_HELP_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${TAURI_PACKAGE_VERSION}" ]]; then
  echo "Version mismatch detected across release-critical docs"
  exit 1
fi

echo "Version consistency check passed (${CHANGELOG_VERSION})"
