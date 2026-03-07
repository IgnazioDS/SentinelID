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

extract_json_value_or_fail() {
  local label="$1"
  local path="$2"
  local key_path="$3"
  local value
  value="$(python3 - "${path}" "${key_path}" <<'PY'
import json
import sys

path = sys.argv[1]
key_path = sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    payload = json.load(f)
current = payload
for segment in key_path.split("."):
    if isinstance(current, dict):
        current = current.get(segment, "")
    else:
        current = ""
        break
print(current if isinstance(current, str) else "")
PY
)"
  extract_or_fail "${label}" "${value}"
}

CHANGELOG_VERSION="$(extract_or_fail "CHANGELOG.md" "$(sed -nE 's/^## v([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' CHANGELOG.md | head -n 1)")"
RUNBOOK_VERSION="$(extract_or_fail "RUNBOOK.md" "$(sed -nE 's/^# SentinelID Runbook \(v([0-9]+\.[0-9]+\.[0-9]+)\).*/\1/p' RUNBOOK.md | head -n 1)")"
RELEASE_GUIDE_VERSION="$(extract_or_fail "docs/RELEASE.md" "$(sed -nE 's/^# Release Guide \(v([0-9]+\.[0-9]+\.[0-9]+)\).*/\1/p' docs/RELEASE.md | head -n 1)")"
PACKAGING_GUIDE_VERSION="$(extract_or_fail "docs/PACKAGING.md" "$(sed -nE 's/^# Desktop Packaging \(v([0-9]+\.[0-9]+\.[0-9]+)\).*/\1/p' docs/PACKAGING.md | head -n 1)")"
RECOVERY_GUIDE_VERSION="$(extract_or_fail "docs/RECOVERY.md" "$(sed -nE 's/^# Telemetry Recovery \(v([0-9]+\.[0-9]+\.[0-9]+)\).*/\1/p' docs/RECOVERY.md | head -n 1)")"
DEMO_CHECKLIST_VERSION="$(extract_or_fail "docs/DEMO_CHECKLIST.md" "$(sed -nE 's/^# SentinelID Demo Checklist \(v([0-9]+\.[0-9]+\.[0-9]+)\).*/\1/p' docs/DEMO_CHECKLIST.md | head -n 1)")"
PILOT_FREEZE_VERSION="$(extract_or_fail "docs/PILOT_FREEZE.md" "$(sed -nE 's/^# Pilot Readiness Freeze \(v([0-9]+\.[0-9]+\.[0-9]+) target\).*/\1/p' docs/PILOT_FREEZE.md | head -n 1)")"
MAKE_HELP_VERSION="$(extract_or_fail "Makefile help banner" "$(sed -nE 's/.*SentinelID v([0-9]+\.[0-9]+\.[0-9]+) Commands.*/\1/p' Makefile | head -n 1)")"
DESKTOP_PACKAGE_VERSION="$(extract_json_value_or_fail "apps/desktop/package.json" "apps/desktop/package.json" "version")"
DESKTOP_PACKAGE_LOCK_VERSION="$(extract_json_value_or_fail "apps/desktop/package-lock.json" "apps/desktop/package-lock.json" "version")"
TAURI_ROOT_VERSION="$(extract_json_value_or_fail "apps/desktop/tauri.conf.json" "apps/desktop/tauri.conf.json" "package.version")"
TAURI_PACKAGE_VERSION="$(extract_json_value_or_fail "apps/desktop/src-tauri/tauri.conf.json" "apps/desktop/src-tauri/tauri.conf.json" "package.version")"
TAURI_DEV_VERSION="$(extract_json_value_or_fail "apps/desktop/src-tauri/tauri.dev.conf.json" "apps/desktop/src-tauri/tauri.dev.conf.json" "package.version")"
CLOUD_APP_VERSION="$(extract_or_fail "apps/cloud/main.py" "$(sed -nE 's/^[[:space:]]*version=\"([0-9]+\.[0-9]+\.[0-9]+)\",/\1/p' apps/cloud/main.py | head -n 1)")"
PILOT_EVIDENCE_INDEX_VERSION="$(extract_or_fail "scripts/release/build_pilot_evidence_index.sh" "$(sed -nE 's/^SentinelID Pilot Readiness Checklist \(v([0-9]+\.[0-9]+\.[0-9]+) target\).*/\1/p' scripts/release/build_pilot_evidence_index.sh | head -n 1)")"

echo "Detected versions:"
echo "  changelog=${CHANGELOG_VERSION}"
echo "  runbook=${RUNBOOK_VERSION}"
echo "  release_guide=${RELEASE_GUIDE_VERSION}"
echo "  packaging_guide=${PACKAGING_GUIDE_VERSION}"
echo "  recovery_guide=${RECOVERY_GUIDE_VERSION}"
echo "  demo_checklist=${DEMO_CHECKLIST_VERSION}"
echo "  pilot_freeze=${PILOT_FREEZE_VERSION}"
echo "  make_help=${MAKE_HELP_VERSION}"
echo "  desktop_package=${DESKTOP_PACKAGE_VERSION}"
echo "  desktop_package_lock=${DESKTOP_PACKAGE_LOCK_VERSION}"
echo "  desktop_tauri_root=${TAURI_ROOT_VERSION}"
echo "  tauri_package=${TAURI_PACKAGE_VERSION}"
echo "  tauri_dev=${TAURI_DEV_VERSION}"
echo "  cloud_app=${CLOUD_APP_VERSION}"
echo "  pilot_evidence_index=${PILOT_EVIDENCE_INDEX_VERSION}"

if [[ "${CHANGELOG_VERSION}" != "${RUNBOOK_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${RELEASE_GUIDE_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${PACKAGING_GUIDE_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${RECOVERY_GUIDE_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${DEMO_CHECKLIST_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${PILOT_FREEZE_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${MAKE_HELP_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${DESKTOP_PACKAGE_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${DESKTOP_PACKAGE_LOCK_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${TAURI_ROOT_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${TAURI_PACKAGE_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${TAURI_DEV_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${CLOUD_APP_VERSION}" ]] \
  || [[ "${CHANGELOG_VERSION}" != "${PILOT_EVIDENCE_INDEX_VERSION}" ]]; then
  echo "Version mismatch detected across release-critical docs"
  exit 1
fi

echo "Version consistency check passed (${CHANGELOG_VERSION})"
