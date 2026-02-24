#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

FRAME_DATA_URL = (
    "data:image/jpeg;base64,"
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxISEhUTEhIVFhUXFRUVFRUVFRUVFRUXFhUX"
    "FhUVFRUYHSggGBolHRUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0lHyUtLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMB"
    "IgACEQEDEQH/xAAXAAADAQAAAAAAAAAAAAAAAAAAAQID/8QAFhABAQEAAAAAAAAAAAAAAAAA"
    "AAER/8QAFgEBAQEAAAAAAAAAAAAAAAAAAgAB/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwD"
    "AQACEQMRAD8A0wD/AP/Z"
)


def post_json(base_url: str, token: str, path: str, payload: dict) -> tuple[dict, float]:
    for retry in range(6):
        req = urllib.request.Request(
            f"{base_url}{path}",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body, (time.perf_counter() - started) * 1000.0
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and retry < 5:
                time.sleep(0.5 + retry * 0.5)
                continue
            raise
    raise RuntimeError(f"Failed request for {path}: retries exhausted")


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = (len(values) - 1) * (p / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    if lo == hi:
        return float(values[lo])
    frac = idx - lo
    return float(values[lo] * (1.0 - frac) + values[hi] * frac)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark edge auth/frame latency.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--token", default="devtoken")
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    frame_latencies: list[float] = []
    finish_latencies: list[float] = []
    total_latencies: list[float] = []

    for attempt in range(args.attempts):
        started = time.perf_counter()
        start_payload, _ = post_json(args.base_url, args.token, "/api/v1/auth/start", {})
        session_id = start_payload["session_id"]

        for _ in range(args.frames):
            _, latency = post_json(
                args.base_url,
                args.token,
                "/api/v1/auth/frame",
                {"session_id": session_id, "frame": FRAME_DATA_URL},
            )
            frame_latencies.append(latency)
            time.sleep(0.10)

        finish_payload, finish_latency = post_json(
            args.base_url, args.token, "/api/v1/auth/finish", {"session_id": session_id}
        )
        if finish_payload.get("decision") == "step_up":
            for _ in range(args.frames):
                _, latency = post_json(
                    args.base_url,
                    args.token,
                    "/api/v1/auth/frame",
                    {"session_id": session_id, "frame": FRAME_DATA_URL},
                )
                frame_latencies.append(latency)
                time.sleep(0.10)
            _, finish_latency = post_json(
                args.base_url, args.token, "/api/v1/auth/finish", {"session_id": session_id}
            )
        finish_latencies.append(finish_latency)
        total_latencies.append((time.perf_counter() - started) * 1000.0)
        time.sleep(0.3)

    result = {
        "attempts": args.attempts,
        "frames_per_attempt": args.frames,
        "frame_count": len(frame_latencies),
        "frame_latency_ms": {
            "mean": round(statistics.fmean(frame_latencies), 2) if frame_latencies else 0.0,
            "p50": round(percentile(frame_latencies, 50), 2),
            "p95": round(percentile(frame_latencies, 95), 2),
        },
        "finish_latency_ms": {
            "mean": round(statistics.fmean(finish_latencies), 2) if finish_latencies else 0.0,
            "p50": round(percentile(finish_latencies, 50), 2),
            "p95": round(percentile(finish_latencies, 95), 2),
        },
        "attempt_latency_ms": {
            "mean": round(statistics.fmean(total_latencies), 2) if total_latencies else 0.0,
            "p50": round(percentile(total_latencies, 50), 2),
            "p95": round(percentile(total_latencies, 95), 2),
        },
    }

    print(json.dumps(result, indent=2))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
