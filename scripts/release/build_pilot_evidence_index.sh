#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

EVIDENCE_DIR="${ROOT_DIR}/output/release"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK_DIR="${EVIDENCE_DIR}/pilot_evidence_${STAMP}"
TARBALL_PATH="${EVIDENCE_DIR}/pilot_evidence_${STAMP}.tar.gz"

RELIABILITY_FILE="${ROOT_DIR}/output/ci/reliability_slo.json"
PERF_DIR="${ROOT_DIR}/scripts/perf/out"
SUPPORT_DIR="${ROOT_DIR}/scripts/support/out"
CI_PARITY_PR_URL="${CI_PARITY_PR_URL:-}"
CI_PARITY_MAIN_URL="${CI_PARITY_MAIN_URL:-}"
RELEASE_TAG_DISPATCH_URL="${RELEASE_TAG_DISPATCH_URL:-}"
RUNBOOK_LOCK_LABEL="${RUNBOOK_LOCK_LABEL:-}"

autodetect_ci_url() {
  local event="$1"
  if ! command -v gh >/dev/null 2>&1; then
    return
  fi

  gh run list \
    --workflow release-parity.yml \
    --limit 30 \
    --json event,status,conclusion,url,createdAt \
    --jq "map(select(.event == \"${event}\" and .status == \"completed\" and .conclusion == \"success\")) | sort_by(.createdAt) | reverse | .[0].url // \"\"" \
    2>/dev/null || true
}

autodetect_release_tag_dispatch_url() {
  if ! command -v gh >/dev/null 2>&1; then
    return
  fi

  gh run list \
    --workflow release-tag.yml \
    --limit 30 \
    --json event,status,conclusion,url,createdAt,headBranch \
    --jq 'map(select(.event == "workflow_dispatch" and .status == "completed" and .conclusion == "success" and .headBranch == "main")) | sort_by(.createdAt) | reverse | .[0].url // ""' \
    2>/dev/null || true
}

if [[ -z "${CI_PARITY_PR_URL}" ]]; then
  CI_PARITY_PR_URL="$(autodetect_ci_url "pull_request")"
fi
if [[ -z "${CI_PARITY_MAIN_URL}" ]]; then
  CI_PARITY_MAIN_URL="$(autodetect_ci_url "push")"
fi
if [[ -z "${RELEASE_TAG_DISPATCH_URL}" ]]; then
  RELEASE_TAG_DISPATCH_URL="$(autodetect_release_tag_dispatch_url)"
fi

mkdir -p "${WORK_DIR}/docs"

if [[ ! -f "${RELIABILITY_FILE}" ]]; then
  echo "Missing reliability report: ${RELIABILITY_FILE}"
  exit 1
fi

LATEST_PERF="$(ls -1t "${PERF_DIR}"/bench_edge_*.json 2>/dev/null | head -n 1 || true)"
LATEST_SUPPORT="$(ls -1t "${SUPPORT_DIR}"/support_bundle_*.tar.gz 2>/dev/null | head -n 1 || true)"
LATEST_RELEASE_EVIDENCE="$(ls -1t "${EVIDENCE_DIR}"/evidence_pack_*.tar.gz 2>/dev/null | head -n 1 || true)"
LATEST_RUNBOOK_LOCK=""
if [[ -n "${RUNBOOK_LOCK_LABEL}" && -f "${EVIDENCE_DIR}/runbook_lock_${RUNBOOK_LOCK_LABEL}.tar.gz" ]]; then
  LATEST_RUNBOOK_LOCK="${EVIDENCE_DIR}/runbook_lock_${RUNBOOK_LOCK_LABEL}.tar.gz"
else
  LATEST_RUNBOOK_LOCK="$(ls -1t "${EVIDENCE_DIR}"/runbook_lock_*.tar.gz 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${LATEST_PERF}" ]]; then
  echo "No perf artifact found under ${PERF_DIR}"
  exit 1
fi
if [[ -z "${LATEST_SUPPORT}" ]]; then
  echo "No support bundle artifact found under ${SUPPORT_DIR}"
  exit 1
fi
if [[ -z "${LATEST_RELEASE_EVIDENCE}" ]]; then
  echo "No release evidence pack found under ${EVIDENCE_DIR}; generating one now..."
  "${ROOT_DIR}/scripts/release/build_evidence_pack.sh"
  LATEST_RELEASE_EVIDENCE="$(ls -1t "${EVIDENCE_DIR}"/evidence_pack_*.tar.gz 2>/dev/null | head -n 1 || true)"
fi
if [[ -z "${LATEST_RELEASE_EVIDENCE}" ]]; then
  echo "Release evidence pack generation failed"
  exit 1
fi
if [[ -z "${LATEST_RUNBOOK_LOCK}" ]]; then
  echo "No runbook lock artifact found under ${EVIDENCE_DIR}; generating one now..."
  if [[ -n "${RUNBOOK_LOCK_LABEL}" ]]; then
    RUNBOOK_LOCK_LABEL="${RUNBOOK_LOCK_LABEL}" "${ROOT_DIR}/scripts/release/build_runbook_lock.sh"
  else
    "${ROOT_DIR}/scripts/release/build_runbook_lock.sh"
  fi
  if [[ -n "${RUNBOOK_LOCK_LABEL}" && -f "${EVIDENCE_DIR}/runbook_lock_${RUNBOOK_LOCK_LABEL}.tar.gz" ]]; then
    LATEST_RUNBOOK_LOCK="${EVIDENCE_DIR}/runbook_lock_${RUNBOOK_LOCK_LABEL}.tar.gz"
  else
    LATEST_RUNBOOK_LOCK="$(ls -1t "${EVIDENCE_DIR}"/runbook_lock_*.tar.gz 2>/dev/null | head -n 1 || true)"
  fi
fi
if [[ -z "${LATEST_RUNBOOK_LOCK}" ]]; then
  echo "Runbook lock artifact generation failed"
  exit 1
fi

cp "${RELIABILITY_FILE}" "${WORK_DIR}/reliability_slo.json"
cp "${LATEST_PERF}" "${WORK_DIR}/bench_edge_latest.json"
cp "${LATEST_SUPPORT}" "${WORK_DIR}/support_bundle_latest.tar.gz"
cp "${LATEST_RELEASE_EVIDENCE}" "${WORK_DIR}/release_evidence_pack.tar.gz"
cp "${LATEST_RUNBOOK_LOCK}" "${WORK_DIR}/runbook_lock_latest.tar.gz"

cp "${ROOT_DIR}/RUNBOOK.md" "${WORK_DIR}/docs/RUNBOOK.md"
cp "${ROOT_DIR}/docs/RELEASE.md" "${WORK_DIR}/docs/RELEASE.md"
cp "${ROOT_DIR}/docs/DEMO_CHECKLIST.md" "${WORK_DIR}/docs/DEMO_CHECKLIST.md"
cp "${ROOT_DIR}/docs/RECOVERY.md" "${WORK_DIR}/docs/RECOVERY.md"
cp "${ROOT_DIR}/CHANGELOG.md" "${WORK_DIR}/docs/CHANGELOG.md"

if [[ -n "${RELEASE_CHECK_LOG:-}" && -f "${RELEASE_CHECK_LOG}" ]]; then
  cp "${RELEASE_CHECK_LOG}" "${WORK_DIR}/release_check.log"
fi

cat > "${WORK_DIR}/pilot_checklist.txt" <<'CHECKLIST'
SentinelID Pilot Readiness Checklist (v2.3.1 target)

- [ ] Fresh machine setup from RUNBOOK.md
- [ ] Docker-first startup (demo-up + admin UI reachability)
- [ ] make release-check passes
- [ ] make demo-verify passes
- [ ] Recovery outage simulation passes
- [ ] Support bundle sanitization verified
- [ ] Evidence pack generated and attached
- [ ] CI parity proof collected (PR + main)
- [ ] Manual release-tag workflow_dispatch proof collected
- [ ] Known-good runbook lock artifact archived
CHECKLIST

python3 - "${WORK_DIR}" "${LATEST_PERF}" "${LATEST_SUPPORT}" "${LATEST_RELEASE_EVIDENCE}" "${LATEST_RUNBOOK_LOCK}" "${CI_PARITY_PR_URL}" "${CI_PARITY_MAIN_URL}" "${RELEASE_TAG_DISPATCH_URL}" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

work_dir = Path(sys.argv[1])
latest_perf = Path(sys.argv[2])
latest_support = Path(sys.argv[3])
release_pack = Path(sys.argv[4])
runbook_lock = Path(sys.argv[5])
ci_parity_pr_url = sys.argv[6]
ci_parity_main_url = sys.argv[7]
release_tag_dispatch_url = sys.argv[8]


def cmd(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()

manifest = {
    "generated_at": datetime.now(UTC).isoformat(),
    "git": {
        "revision": cmd("git", "rev-parse", "HEAD"),
        "short_revision": cmd("git", "rev-parse", "--short", "HEAD"),
        "branch": cmd("git", "rev-parse", "--abbrev-ref", "HEAD"),
    },
    "artifacts": {
        "reliability_slo": "reliability_slo.json",
        "bench_edge_latest": "bench_edge_latest.json",
        "support_bundle_latest": "support_bundle_latest.tar.gz",
        "release_evidence_pack": "release_evidence_pack.tar.gz",
        "runbook_lock_latest": "runbook_lock_latest.tar.gz",
        "docs": {
            "runbook": "docs/RUNBOOK.md",
            "release": "docs/RELEASE.md",
            "demo_checklist": "docs/DEMO_CHECKLIST.md",
            "recovery": "docs/RECOVERY.md",
            "changelog": "docs/CHANGELOG.md",
        },
        "pilot_checklist": "pilot_checklist.txt",
    },
    "source_paths": {
        "bench_edge_latest": str(latest_perf),
        "support_bundle_latest": str(latest_support),
        "release_evidence_pack": str(release_pack),
        "runbook_lock_latest": str(runbook_lock),
    },
    "notes": {
        "release_check_log": "release_check.log" if (work_dir / "release_check.log").exists() else "",
        "ci_parity_proof_pr": ci_parity_pr_url,
        "ci_parity_proof_main": ci_parity_main_url,
        "ci_parity_note": "If empty, capture URLs after CI completes on PR/main.",
        "release_tag_dispatch_proof": release_tag_dispatch_url,
        "release_tag_dispatch_note": "Optional post-release proof from a successful workflow_dispatch run of release-tag.yml on main.",
    },
}

(work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY

cat > "${WORK_DIR}/README.txt" <<README
SentinelID Pilot Evidence Index
Generated: ${STAMP}

Included files:
- manifest.json
- pilot_checklist.txt
- reliability_slo.json
- bench_edge_latest.json
- support_bundle_latest.tar.gz
- release_evidence_pack.tar.gz
- runbook_lock_latest.tar.gz
- docs/ (RUNBOOK, RELEASE, DEMO_CHECKLIST, RECOVERY, CHANGELOG)
README

tar -czf "${TARBALL_PATH}" -C "${EVIDENCE_DIR}" "pilot_evidence_${STAMP}"

echo "Pilot evidence index created:"
for artifact in "${WORK_DIR}" "${TARBALL_PATH}"; do
  echo "  ${artifact}"
done
