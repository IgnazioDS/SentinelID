from __future__ import annotations

import asyncio

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from sentinelid_edge.core.config import settings
from sentinelid_edge.main import LocalhostOnlyMiddleware, app


def _request_with_client(path: str, host: str) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "client": (host, 12345),
        "server": ("127.0.0.1", 8787),
    }
    return Request(scope)


def test_localhost_client_reaches_auth_layer() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/settings/telemetry")
    # Local/test loopback request is allowed through, then auth is enforced.
    assert resp.status_code == 401


def test_non_local_client_is_rejected_by_localhost_middleware() -> None:
    middleware = LocalhostOnlyMiddleware(app)
    request = _request_with_client("/api/v1/settings/telemetry", "8.8.8.8")

    async def _call_next(_: Request):
        return JSONResponse(status_code=200, content={"status": "ok"})

    response = asyncio.run(middleware.dispatch(request, _call_next))
    assert response.status_code == 403


def test_non_local_client_can_access_health_paths() -> None:
    middleware = LocalhostOnlyMiddleware(app)

    async def _call_next(_: Request):
        return JSONResponse(status_code=200, content={"status": "ok"})

    response_api = asyncio.run(
        middleware.dispatch(_request_with_client("/api/v1/health", "203.0.113.10"), _call_next)
    )
    response_root = asyncio.run(
        middleware.dispatch(_request_with_client("/health", "203.0.113.10"), _call_next)
    )

    assert response_api.status_code == 200
    assert response_root.status_code == 200
