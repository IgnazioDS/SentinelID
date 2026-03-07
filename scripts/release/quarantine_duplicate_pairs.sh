#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

TARGET_DIR="${DUPLICATE_QUARANTINE_TARGET_DIR:-apps/desktop/resources/edge/app}"
QUARANTINE_BASE="${DUPLICATE_QUARANTINE_BASE:-output/release/duplicate_quarantine}"

if [[ ! -d "${TARGET_DIR}" ]]; then
  echo "[skip] duplicate quarantine target not found: ${TARGET_DIR}"
  exit 0
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
quarantine_dir="${QUARANTINE_BASE}/${timestamp}"
moved=0
skipped_tracked=0

is_tracked() {
  local rel_path="$1"
  git ls-files --error-unmatch -- "${rel_path}" >/dev/null 2>&1
}

while IFS= read -r -d '' path; do
  rel_path="${path#./}"
  base="${rel_path##*/}"
  dir="${rel_path%/*}"

  if [[ "${base}" =~ ^(.+)\ [0-9]+(\..+)?$ ]]; then
    original="${BASH_REMATCH[1]}${BASH_REMATCH[2]:-}"
    original_rel="${dir}/${original}"

    if [[ ! -e "${original_rel}" ]]; then
      continue
    fi

    if is_tracked "${rel_path}"; then
      echo "[keep] tracked duplicate remains for explicit guard: ${rel_path}"
      skipped_tracked=$((skipped_tracked + 1))
      continue
    fi

    dest="${quarantine_dir}/${rel_path}"
    mkdir -p "$(dirname "${dest}")"
    mv "${rel_path}" "${dest}"
    echo "[move] ${rel_path} -> ${dest}"
    moved=$((moved + 1))
  fi
done < <(find "${TARGET_DIR}" -mindepth 1 -print0)

if [[ "${moved}" -eq 0 ]]; then
  echo "No untracked duplicate artifacts quarantined"
else
  echo "Quarantined ${moved} untracked duplicate artifact(s) under ${quarantine_dir}"
fi

if [[ "${skipped_tracked}" -gt 0 ]]; then
  echo "Tracked duplicates were left in place (${skipped_tracked}); duplicate guard will enforce failure."
fi

