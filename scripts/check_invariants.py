#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tarfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import ipaddress

REQUIRED_SUPPORT_FILES = [
    "devices.json",
    "environment.json",
    "events.json",
    "stats.json",
]


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    data: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        payload = {
            "status": self.status,
            "detail": self.detail,
        }
        payload.update(self.data)
        return payload


def is_loopback_url(url: str) -> tuple[bool, str]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if not host:
        return False, "missing hostname"
    if host.lower() in {"localhost", "127.0.0.1", "::1"}:
        return True, host
    try:
        return ipaddress.ip_address(host).is_loopback, host
    except ValueError:
        return False, host


def request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: dict[str, object] | None = None,
    timeout: float = 20.0,
) -> tuple[int, dict[str, str], bytes]:
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, method=method, data=data, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()


def check_loopback(name: str, url: str) -> CheckResult:
    ok, host = is_loopback_url(url)
    detail = f"{name} uses loopback host {host}" if ok else f"{name} must use a loopback host, got {host}"
    return CheckResult(
        name=f"{name}_loopback_binding",
        status="pass" if ok else "fail",
        detail=detail,
        data={"url": url, "host": host},
    )


def check_edge_bearer(edge_url: str, edge_token: str) -> CheckResult:
    endpoint = edge_url.rstrip("/") + "/api/v1/settings/telemetry"
    missing_status, _, _ = request("GET", endpoint)
    invalid_status, _, _ = request(
        "GET",
        endpoint,
        headers={"Authorization": "Bearer invalid-token"},
    )
    valid_status, headers, body = request(
        "GET",
        endpoint,
        headers={"Authorization": f"Bearer {edge_token}"},
    )
    passed = missing_status == 401 and invalid_status == 401 and valid_status == 200
    detail = (
        "edge bearer enforcement behaves as expected"
        if passed
        else (
            "expected edge bearer statuses 401/401/200 for missing/invalid/valid auth, got "
            f"{missing_status}/{invalid_status}/{valid_status}"
        )
    )
    payload: dict[str, object] = {
        "endpoint": endpoint,
        "missing_auth_status": missing_status,
        "invalid_auth_status": invalid_status,
        "valid_auth_status": valid_status,
        "request_id": headers.get("x-request-id"),
    }
    if body:
        try:
            payload["valid_body"] = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload["valid_body"] = body.decode("utf-8", errors="replace")
    return CheckResult("edge_bearer_enforcement", "pass" if passed else "fail", detail, payload)


def check_cloud_admin_token(cloud_url: str, admin_token: str) -> CheckResult:
    endpoint = cloud_url.rstrip("/") + "/v1/admin/stats"
    missing_status, _, _ = request("GET", endpoint)
    invalid_status, _, _ = request(
        "GET",
        endpoint,
        headers={"X-Admin-Token": "invalid-token"},
    )
    valid_status, headers, body = request(
        "GET",
        endpoint,
        headers={"X-Admin-Token": admin_token},
    )
    passed = missing_status == 401 and invalid_status == 401 and valid_status == 200
    detail = (
        "cloud admin token enforcement behaves as expected"
        if passed
        else (
            "expected cloud admin statuses 401/401/200 for missing/invalid/valid token, got "
            f"{missing_status}/{invalid_status}/{valid_status}"
        )
    )
    payload: dict[str, object] = {
        "endpoint": endpoint,
        "missing_token_status": missing_status,
        "invalid_token_status": invalid_status,
        "valid_token_status": valid_status,
        "request_id": headers.get("x-request-id"),
    }
    if body:
        try:
            payload["valid_body_keys"] = sorted(json.loads(body.decode("utf-8")).keys())
        except json.JSONDecodeError:
            payload["valid_body_keys"] = []
    return CheckResult("cloud_admin_token_enforcement", "pass" if passed else "fail", detail, payload)


def check_support_bundle(cloud_url: str, admin_token: str) -> CheckResult:
    endpoint = cloud_url.rstrip("/") + "/v1/admin/support-bundle?window=24h&events_limit=25"
    status, headers, body = request("POST", endpoint, headers={"X-Admin-Token": admin_token})
    content_type = headers.get("content-type", "")
    disposition = headers.get("content-disposition", "")
    created_at = headers.get("x-support-bundle-created-at")
    names: list[str] = []
    archive_error = ""
    if status == 200:
        try:
            with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as archive:
                names = sorted(archive.getnames())
        except tarfile.TarError as exc:
            archive_error = str(exc)
    required_present = all(name in names for name in REQUIRED_SUPPORT_FILES)
    passed = (
        status == 200
        and content_type == "application/gzip"
        and "attachment;" in disposition
        and bool(created_at)
        and not archive_error
        and required_present
    )
    detail = (
        "support bundle endpoint returns the expected sanitized tarball contract"
        if passed
        else (
            "support bundle contract mismatch: "
            f"status={status} content_type={content_type!r} created_at={bool(created_at)} "
            f"archive_error={archive_error or 'none'} required_present={required_present}"
        )
    )
    return CheckResult(
        "support_bundle_endpoint",
        "pass" if passed else "fail",
        detail,
        {
            "endpoint": endpoint,
            "status_code": status,
            "content_type": content_type,
            "content_disposition": disposition,
            "created_at": created_at,
            "bundle_members": names,
            "required_members": REQUIRED_SUPPORT_FILES,
            "archive_error": archive_error,
            "bytes": len(body),
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check SentinelID runtime invariants.")
    parser.add_argument("--edge-url", default="http://127.0.0.1:8787")
    parser.add_argument("--edge-token", default="devtoken")
    parser.add_argument("--cloud-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-token", default="dev-admin-token")
    parser.add_argument("--out", default="output/ci/invariant_report.json")
    return parser.parse_args()


def run_check(name: str, fn) -> CheckResult:
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - exercised via subprocess tests
        return CheckResult(
            name,
            "fail",
            f"{name} raised {exc.__class__.__name__}: {exc}",
            {"traceback": traceback.format_exc(limit=5)},
        )


def main() -> int:
    args = parse_args()
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    checks: list[CheckResult] = []

    edge_loopback = run_check("edge_loopback_binding", lambda: check_loopback("edge", args.edge_url))
    cloud_loopback = run_check("cloud_loopback_binding", lambda: check_loopback("cloud", args.cloud_url))
    checks.extend([edge_loopback, cloud_loopback])

    if edge_loopback.status == "pass":
        checks.append(
            run_check(
                "edge_bearer_enforcement",
                lambda: check_edge_bearer(args.edge_url, args.edge_token),
            )
        )
    else:
        checks.append(
            CheckResult(
                "edge_bearer_enforcement",
                "skipped",
                "edge bearer enforcement skipped because edge loopback binding failed",
                {"endpoint": args.edge_url.rstrip("/") + "/api/v1/settings/telemetry"},
            )
        )

    if cloud_loopback.status == "pass":
        checks.append(
            run_check(
                "cloud_admin_token_enforcement",
                lambda: check_cloud_admin_token(args.cloud_url, args.admin_token),
            )
        )
        checks.append(
            run_check(
                "support_bundle_endpoint",
                lambda: check_support_bundle(args.cloud_url, args.admin_token),
            )
        )
    else:
        checks.append(
            CheckResult(
                "cloud_admin_token_enforcement",
                "skipped",
                "cloud admin token enforcement skipped because cloud loopback binding failed",
                {"endpoint": args.cloud_url.rstrip("/") + "/v1/admin/stats"},
            )
        )
        checks.append(
            CheckResult(
                "support_bundle_endpoint",
                "skipped",
                "support bundle probe skipped because cloud loopback binding failed",
                {"endpoint": args.cloud_url.rstrip("/") + "/v1/admin/support-bundle?window=24h&events_limit=25"},
            )
        )

    failures = [check.name for check in checks if check.status == "fail"]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "status": "pass" if not failures else "fail",
        "edge_url": args.edge_url,
        "cloud_url": args.cloud_url,
        "checks": {check.name: check.as_dict() for check in checks},
        "failed_checks": failures,
    }
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for check in checks:
        prefix = "[ok]" if check.status == "pass" else "[skip]" if check.status == "skipped" else "[fail]"
        print(f"{prefix} {check.name}: {check.detail}")
    print(f"Invariant report written to {output_path}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
