#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

DOCS=(
  "RUNBOOK.md"
  "docs/RELEASE.md"
  "docs/PACKAGING.md"
  "docs/RECOVERY.md"
  "docs/DEMO_CHECKLIST.md"
)

FAILED=0

have_rg() {
  command -v rg >/dev/null 2>&1
}

search_fixed() {
  local pattern="$1"
  shift
  if have_rg; then
    rg -n --fixed-strings "${pattern}" "$@" || true
  else
    grep -RFn -- "${pattern}" "$@" || true
  fi
}

search_regex() {
  local pattern="$1"
  shift
  if have_rg; then
    rg -n "${pattern}" "$@" || true
  else
    grep -REn -- "${pattern}" "$@" || true
  fi
}

contains_fixed() {
  local pattern="$1"
  shift
  if have_rg; then
    rg -q --fixed-strings "${pattern}" "$@"
  else
    grep -RFq -- "${pattern}" "$@"
  fi
}

check_disallowed_fixed() {
  local pattern="$1"
  local guidance="$2"
  local matches
  matches="$(search_fixed "${pattern}" "${DOCS[@]}")"
  if [[ -n "${matches}" ]]; then
    echo "Disallowed docs reference found: ${pattern}"
    echo "${matches}"
    echo "Use: ${guidance}"
    FAILED=1
  fi
}

check_disallowed_regex() {
  local pattern="$1"
  local guidance="$2"
  local matches
  matches="$(search_regex "${pattern}" "${DOCS[@]}")"
  if [[ -n "${matches}" ]]; then
    echo "Disallowed docs reference found: ${pattern}"
    echo "${matches}"
    echo "Use: ${guidance}"
    FAILED=1
  fi
}

require_fixed() {
  local file="$1"
  local pattern="$2"
  if ! contains_fixed "${pattern}" "${file}"; then
    echo "Missing required docs guidance in ${file}: ${pattern}"
    FAILED=1
  fi
}

check_disallowed_fixed "./scripts/build_and_smoke_desktop.sh" "make bundle-edge && make build-desktop"
check_disallowed_fixed "./scripts/smoke_test_bundling.sh" "make smoke-bundling"
check_disallowed_fixed "./scripts/smoke_test_desktop.sh" "make smoke-desktop"
check_disallowed_fixed "./scripts/smoke_test_cloud_recovery.sh" "make smoke-cloud-recovery"
check_disallowed_fixed "./scripts/support_bundle.sh" "make support-bundle"
check_disallowed_fixed "./scripts/check_local_support_bundle_sanitization.sh" "make check-local-support-bundle"
check_disallowed_fixed "./scripts/check_invariants.py" "make check-invariants"
check_disallowed_fixed "./scripts/release/check_version_consistency.sh" "make check-version-consistency"
check_disallowed_fixed "./scripts/release/check_release_tag_alignment.sh" "make check-release-tag"
check_disallowed_fixed "docker compose up --build" "make demo-up"
check_disallowed_regex "\\bADMIN_TOKEN\\b" "Use ADMIN_API_TOKEN in docs; ADMIN_TOKEN is an internal override only."
check_disallowed_regex "\\bNEXT_PUBLIC_ADMIN_TOKEN\\b" "Use ADMIN_API_TOKEN and server-side injection guidance only."
check_disallowed_regex "\\bVITE_ADMIN_TOKEN\\b" "Use ADMIN_API_TOKEN and the canonical Make workflows."

if find docs -maxdepth 1 -type f -iname 'phase*.md' | grep -q .; then
  echo "Legacy phase docs are still present in docs/ root:"
  find docs -maxdepth 1 -type f -iname 'phase*.md' | sort
  FAILED=1
fi

require_fixed "RUNBOOK.md" "make install-dev"
require_fixed "RUNBOOK.md" "make demo-up"
require_fixed "RUNBOOK.md" "make demo-verify"
require_fixed "RUNBOOK.md" "make demo"
require_fixed "RUNBOOK.md" "make demo-down"
require_fixed "docs/RELEASE.md" "make release-check"
require_fixed "docs/RELEASE.md" "make check-version-consistency"
require_fixed "docs/RELEASE.md" "make check-docs-consistency"
require_fixed "docs/PACKAGING.md" "make bundle-edge"
require_fixed "docs/PACKAGING.md" "make build-desktop"
require_fixed "docs/PACKAGING.md" "make smoke-bundling"
require_fixed "docs/RECOVERY.md" "make smoke-cloud-recovery"
require_fixed "docs/RECOVERY.md" "make support-bundle"

if [[ "${FAILED}" -ne 0 ]]; then
  exit 1
fi

echo "Docs consistency check passed"
