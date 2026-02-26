#!/usr/bin/env bash
set -euo pipefail

baseline="${ORPHAN_BASELINE_PIDS:-}"
matches="$(pgrep -fl "run_edge.sh|sentinelid_edge.main:app" || true)"

if [[ -n "${baseline}" && -n "${matches}" ]]; then
  filtered=""
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    pid="${line%% *}"
    if [[ ",${baseline}," == *",${pid},"* ]]; then
      continue
    fi
    filtered+="${line}"$'\n'
  done <<< "${matches}"
  matches="${filtered%$'\n'}"
fi

if [[ -n "${matches}" ]]; then
  echo "Found potential orphan edge process(es):"
  echo "${matches}"
  exit 1
fi

echo "No orphan edge processes detected"
