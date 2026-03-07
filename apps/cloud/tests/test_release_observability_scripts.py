from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INVARIANT_SCRIPT = REPO_ROOT / "scripts" / "check_invariants.py"
WARNING_BUDGET_SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_desktop_warning_budget.py"
EDGE_TOKEN = "edge-test-token"
ADMIN_TOKEN = "admin-test-token"


def _support_bundle_bytes() -> bytes:
    payloads = {
        "stats.json": {"total_events": 0},
        "events.json": {"events": []},
        "devices.json": {"devices": []},
        "environment.json": {"service": "sentinelid-cloud"},
    }
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in payloads.items():
            raw = json.dumps(payload).encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
    return buffer.getvalue()


class _EdgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/api/v1/settings/telemetry":
            self.send_response(404)
            self.end_headers()
            return

        auth_header = self.headers.get("Authorization")
        if auth_header != f"Bearer {EDGE_TOKEN}":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"unauthorized"}')
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Request-Id", "edge-request-id")
        self.end_headers()
        self.wfile.write(b'{"runtime_available":true}')


class _CloudHandler(BaseHTTPRequestHandler):
    bundle_bytes = _support_bundle_bytes()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _authorized(self) -> bool:
        return self.headers.get("X-Admin-Token") == ADMIN_TOKEN

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/admin/stats":
            self.send_response(404)
            self.end_headers()
            return
        if not self._authorized():
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"unauthorized"}')
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Request-Id", "cloud-request-id")
        self.end_headers()
        self.wfile.write(b'{"total_events":0,"latency_p50_ms":0}')

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/v1/admin/support-bundle"):
            self.send_response(404)
            self.end_headers()
            return
        if not self._authorized():
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"unauthorized"}')
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/gzip")
        self.send_header("Content-Disposition", 'attachment; filename="support_bundle_test.tar.gz"')
        self.send_header("X-Support-Bundle-Created-At", "2026-03-07T00:00:00Z")
        self.end_headers()
        self.wfile.write(self.bundle_bytes)


class _Server:
    def __init__(self, handler_cls: type[BaseHTTPRequestHandler]):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "_Server":
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._server.shutdown()
        self._server.server_close()
        self.thread.join(timeout=5)


def test_check_invariants_reports_success(tmp_path) -> None:
    report_path = tmp_path / "invariant_report.json"
    with _Server(_EdgeHandler) as edge_server, _Server(_CloudHandler) as cloud_server:
        result = subprocess.run(
            [
                sys.executable,
                str(INVARIANT_SCRIPT),
                "--edge-url",
                edge_server.url,
                "--edge-token",
                EDGE_TOKEN,
                "--cloud-url",
                cloud_server.url,
                "--admin-token",
                ADMIN_TOKEN,
                "--out",
                str(report_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["failed_checks"] == []
    assert payload["checks"]["edge_bearer_enforcement"]["valid_auth_status"] == 200
    assert payload["checks"]["cloud_admin_token_enforcement"]["valid_token_status"] == 200
    assert sorted(payload["checks"]["support_bundle_endpoint"]["bundle_members"]) == [
        "devices.json",
        "environment.json",
        "events.json",
        "stats.json",
    ]


def test_check_invariants_fails_for_non_loopback_edge_url(tmp_path) -> None:
    report_path = tmp_path / "invariant_report.json"
    with _Server(_CloudHandler) as cloud_server:
        result = subprocess.run(
            [
                sys.executable,
                str(INVARIANT_SCRIPT),
                "--edge-url",
                "http://192.0.2.10:8787",
                "--edge-token",
                EDGE_TOKEN,
                "--cloud-url",
                cloud_server.url,
                "--admin-token",
                ADMIN_TOKEN,
                "--out",
                str(report_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert "edge_loopback_binding" in payload["failed_checks"]
    assert payload["checks"]["edge_bearer_enforcement"]["status"] == "skipped"


def test_desktop_warning_budget_parser_passes_within_budget(tmp_path) -> None:
    log_path = tmp_path / "desktop.log"
    report_path = tmp_path / "desktop_warning_budget.json"
    log_path.write_text(
        "warning: first issue\n"
        "   --> src-tauri/vendor/wry/src/webview/wkwebview/download.rs:28:17\n"
        "warning: second issue\n"
        "   --> src-tauri/src/main.rs:10:5\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(WARNING_BUDGET_SCRIPT),
            str(log_path),
            "--budget",
            "2",
            "--out",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["warning_count"] == 2
    assert payload["top_sources"][0]["source"] == "src-tauri/vendor/wry/src/webview/wkwebview/download.rs"


def test_desktop_warning_budget_parser_fails_over_budget(tmp_path) -> None:
    log_path = tmp_path / "desktop.log"
    report_path = tmp_path / "desktop_warning_budget.json"
    log_path.write_text(
        "warning: first issue\n"
        "   --> src-tauri/vendor/wry/src/webview/wkwebview/download.rs:28:17\n"
        "warning: second issue\n"
        "   --> src-tauri/src/main.rs:10:5\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(WARNING_BUDGET_SCRIPT),
            str(log_path),
            "--budget",
            "1",
            "--out",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["warning_count"] == 2
    assert payload["over_budget"] is True
