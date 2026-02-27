#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ATTEMPTS="${RELEASE_PARITY_ATTEMPTS:-2}"
if ! [[ "${ATTEMPTS}" =~ ^[0-9]+$ ]] || [[ "${ATTEMPTS}" -lt 1 ]]; then
  echo "RELEASE_PARITY_ATTEMPTS must be a positive integer; got '${ATTEMPTS}'"
  exit 1
fi

LOG_DIR="${ROOT_DIR}/output/ci/logs"
mkdir -p "${LOG_DIR}"

for attempt in $(seq 1 "${ATTEMPTS}"); do
  log_file="${LOG_DIR}/release_check_attempt_${attempt}.log"
  echo "[release-parity] attempt ${attempt}/${ATTEMPTS}"
  set +e
  bash -o pipefail -c "make release-check 2>&1 | tee '${log_file}'"
  status=$?
  set -e

  if [[ "${status}" -eq 0 ]]; then
    echo "[release-parity] success on attempt ${attempt}" | tee "${LOG_DIR}/release_parity_summary.txt"
    exit 0
  fi

  echo "[release-parity] attempt ${attempt} failed with status ${status}"
  if [[ "${attempt}" -lt "${ATTEMPTS}" ]]; then
    echo "[release-parity] cleaning compose stack before retry"
    make demo-down V=1 >/dev/null 2>&1 || true
    sleep 2
  fi
done

echo "[release-parity] failed after ${ATTEMPTS} attempt(s)" | tee "${LOG_DIR}/release_parity_summary.txt"
exit 1
