#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

INCLUDE_GENERATED="${CHECK_DUPLICATE_INCLUDE_GENERATED:-0}"
declare -a DUPLICATES=()

FIND_CMD=(find .)
if [[ "${INCLUDE_GENERATED}" != "1" ]]; then
  FIND_CMD+=(
    \( -type d \(
      -name .git -o
      -name node_modules -o
      -name .next -o
      -name dist -o
      -name build -o
      -name target -o
      -name output -o
      -name .venv -o
      -name venv -o
      -name pyvenv_active -o
      -name pyvenv -o
      -name 'pyvenv_stale*' -o
      -name .sentinelid -o
      -name __pycache__
    \) -prune \)
    -o
  )
fi
FIND_CMD+=(-print0)

while IFS= read -r -d '' path; do
  [[ "${path}" == "." ]] && continue

  base="${path##*/}"
  dir="${path%/*}"

  if [[ "${base}" =~ ^(.+)\ [0-9]+(\..+)?$ ]]; then
    original="${BASH_REMATCH[1]}${BASH_REMATCH[2]:-}"
    if [[ -e "${dir}/${original}" ]]; then
      DUPLICATES+=("${path#./}")
    fi
  fi
done < <("${FIND_CMD[@]}")

if [[ "${#DUPLICATES[@]}" -gt 0 ]]; then
  echo "Duplicate artifact pairs detected (\"<name>\" + \"<name> <n>\"):"
  while IFS= read -r duplicate; do
    [[ -z "${duplicate}" ]] && continue
    printf '  - %s\n' "${duplicate}"
  done < <(printf '%s\n' "${DUPLICATES[@]}" | sort -u)
  echo "Remove these duplicates before running release checks."
  exit 1
fi

echo "No duplicate artifact pairs detected"
