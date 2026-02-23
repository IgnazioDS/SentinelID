#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
TOKEN="${2:-devtoken}"
ATTEMPTS="${3:-6}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/out"
mkdir -p "${OUT_DIR}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${OUT_DIR}/eval_${STAMP}.json"

python3 - "${BASE_URL}" "${TOKEN}" "${ATTEMPTS}" "${OUT_FILE}" <<'PY'
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

base_url = sys.argv[1].rstrip("/")
token = sys.argv[2]
attempts = int(sys.argv[3])
out_file = sys.argv[4]

# Small embedded valid JPEG used only to drive endpoint loops in headless runs.
# No frame bytes are ever persisted to output artifacts.
FRAME_DATA_URL = (
    "data:image/jpeg;base64,"
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxISEhUTEhIVFhUXFRUVFRUVFRUVFRUXFhUX"
    "FhUVFRUYHSggGBolHRUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0lHyUtLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMB"
    "IgACEQEDEQH/xAAXAAADAQAAAAAAAAAAAAAAAAAAAQID/8QAFhABAQEAAAAAAAAAAAAAAAAA"
    "AAER/8QAFgEBAQEAAAAAAAAAAAAAAAAAAgAB/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwD"
    "AQACEQMRAD8A0wD/AP/Z"
)
FRAME_DELAY_SECONDS = 0.13
ATTEMPT_DELAY_SECONDS = 0.6


def post_json(path: str, payload: dict) -> tuple[dict, float]:
    url = f"{base_url}{path}"
    for retry in range(6):
        request = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8")
                latency_ms = (time.perf_counter() - started) * 1000.0
                return json.loads(body), latency_ms
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")
            if err.code == 429 and retry < 5:
                time.sleep(1.0 + retry * 0.5)
                continue
            raise RuntimeError(f"HTTP {err.code} on {path}: {body}") from err

    raise RuntimeError(f"Failed to call {path}: retries exhausted")


def run_attempt(attempt_index: int) -> dict:
    attempt_started = time.perf_counter()
    ts = datetime.now(timezone.utc).isoformat()

    try:
        start_payload, _ = post_json("/api/v1/auth/start", {})
        session_id = start_payload["session_id"]

        # Primary challenge pass.
        for _ in range(8):
            post_json(
                "/api/v1/auth/frame",
                {
                    "session_id": session_id,
                    "frame": FRAME_DATA_URL,
                },
            )
            time.sleep(FRAME_DELAY_SECONDS)

        finish_payload, _ = post_json("/api/v1/auth/finish", {"session_id": session_id})
        step_up_used = bool(finish_payload.get("step_up") and finish_payload.get("decision") == "step_up")

        if step_up_used:
            for _ in range(8):
                post_json(
                    "/api/v1/auth/frame",
                    {
                        "session_id": session_id,
                        "frame": FRAME_DATA_URL,
                    },
                )
                time.sleep(FRAME_DELAY_SECONDS)
            final_payload, _ = post_json("/api/v1/auth/finish", {"session_id": session_id})
        else:
            final_payload = finish_payload

        return {
            "ts": ts,
            "attempt": attempt_index,
            "outcome": final_payload.get("decision", "unknown"),
            "risk_score": final_payload.get("risk_score"),
            "risk_reasons": list(final_payload.get("risk_reasons") or []),
            "liveness_pass": bool(final_payload.get("liveness_passed")),
            "reason_codes": list(final_payload.get("reason_codes") or []),
            "latency_ms": round((time.perf_counter() - attempt_started) * 1000.0, 2),
            "step_up_used": step_up_used,
        }
    except Exception as exc:
        return {
            "ts": ts,
            "attempt": attempt_index,
            "outcome": "error",
            "risk_score": None,
            "risk_reasons": [],
            "liveness_pass": False,
            "reason_codes": ["EVAL_ERROR"],
            "latency_ms": round((time.perf_counter() - attempt_started) * 1000.0, 2),
            "error": str(exc),
            "step_up_used": False,
        }


results = []
for i in range(attempts):
    results.append(run_attempt(i + 1))
    if i < attempts - 1:
        time.sleep(ATTEMPT_DELAY_SECONDS)
output = {
    "eval_version": "v0.7",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "base_url": base_url,
    "attempts": attempts,
    "sanitized": True,
    "results": results,
}

with open(out_file, "w", encoding="utf-8") as fh:
    json.dump(output, fh, indent=2)

print(out_file)
PY

printf 'Wrote eval output: %s\n' "${OUT_FILE}"
