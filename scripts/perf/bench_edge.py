#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
RETRYABLE_HTTP_CODES = {429, 502, 503, 504}
RETRYABLE_NETWORK_ERRORS = (TimeoutError, ConnectionError)


def _http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
    return body[:240]


def post_json(
    base_url: str, token: str, path: str, payload: dict, max_retries: int
) -> tuple[dict, float]:
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    for retry in range(max_retries):
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
            if exc.code in RETRYABLE_HTTP_CODES and retry < (max_retries - 1):
                time.sleep(min(3.0, 0.4 * (2**retry)))
                continue
            body_excerpt = _http_error_body(exc)
            detail = (
                f"{path} failed with HTTP {exc.code} after {retry + 1}/{max_retries} attempts"
            )
            if body_excerpt:
                detail = f"{detail}; body={body_excerpt}"
            raise RuntimeError(detail) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            retryable = isinstance(reason, RETRYABLE_NETWORK_ERRORS)
            if retryable and retry < (max_retries - 1):
                time.sleep(min(3.0, 0.4 * (2**retry)))
                continue
            raise RuntimeError(
                f"{path} failed after {retry + 1}/{max_retries} attempts; network error: {reason}"
            ) from exc
    raise RuntimeError(f"{path} failed after {max_retries} attempts: retries exhausted")


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
    parser.add_argument("--max-retries", type=int, default=6)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    frame_latencies: list[float] = []
    finish_latencies: list[float] = []
    total_latencies: list[float] = []

    for attempt in range(args.attempts):
        started = time.perf_counter()
        start_payload, _ = post_json(
            args.base_url, args.token, "/api/v1/auth/start", {}, args.max_retries
        )
        session_id = start_payload["session_id"]

        for _ in range(args.frames):
            _, latency = post_json(
                args.base_url,
                args.token,
                "/api/v1/auth/frame",
                {"session_id": session_id, "frame": FRAME_DATA_URL},
                args.max_retries,
            )
            frame_latencies.append(latency)
            time.sleep(0.10)

        finish_payload, finish_latency = post_json(
            args.base_url,
            args.token,
            "/api/v1/auth/finish",
            {"session_id": session_id},
            args.max_retries,
        )
        if finish_payload.get("decision") == "step_up":
            for _ in range(args.frames):
                _, latency = post_json(
                    args.base_url,
                    args.token,
                    "/api/v1/auth/frame",
                    {"session_id": session_id, "frame": FRAME_DATA_URL},
                    args.max_retries,
                )
                frame_latencies.append(latency)
                time.sleep(0.10)
            _, finish_latency = post_json(
                args.base_url,
                args.token,
                "/api/v1/auth/finish",
                {"session_id": session_id},
                args.max_retries,
            )
        finish_latencies.append(finish_latency)
        total_latencies.append((time.perf_counter() - started) * 1000.0)
        time.sleep(0.3)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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

    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent / "out" /
        f"bench_edge_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
