import hashlib
import logging
from contextlib import asynccontextmanager
import asyncio
import ipaddress

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from sentinelid_edge.api.router import api_router
from sentinelid_edge.core.config import settings
from sentinelid_edge.core.logging import configure_logging
from sentinelid_edge.core.auth import verify_bearer_token
from sentinelid_edge.core.request_context import (
    clear_request_context,
    generate_request_id,
    set_request_id,
    set_session_id,
)
from sentinelid_edge.services.security.rate_limit import get_rate_limiter
from sentinelid_edge.services.telemetry.exporter import TelemetryExporter
from sentinelid_edge.services.telemetry.runtime import (
    TelemetryRuntime,
    set_telemetry_runtime,
)

logger = logging.getLogger(__name__)

configure_logging(
    service_name="edge",
    log_level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    telemetry_runtime = None
    if settings.TELEMETRY_ENABLED and settings.CLOUD_INGEST_URL:
        exporter = TelemetryExporter(
            cloud_ingest_url=settings.CLOUD_INGEST_URL,
            batch_size=settings.TELEMETRY_BATCH_SIZE,
            max_retries=settings.TELEMETRY_MAX_RETRIES,
            keychain_dir=settings.KEYCHAIN_DIR,
            db_path=settings.DB_PATH,
            http_timeout_seconds=settings.TELEMETRY_HTTP_TIMEOUT_SECONDS,
        )
        telemetry_runtime = TelemetryRuntime(
            exporter=exporter,
            export_interval_seconds=settings.TELEMETRY_EXPORT_INTERVAL_SECONDS,
            signal_queue_size=settings.TELEMETRY_SIGNAL_QUEUE_SIZE,
        )
        set_telemetry_runtime(telemetry_runtime)
        await telemetry_runtime.start()
        logger.info("Telemetry runtime started")
    else:
        set_telemetry_runtime(None)

    try:
        yield
    finally:
        if telemetry_runtime is not None:
            try:
                await telemetry_runtime.stop()
                logger.info("Telemetry runtime stopped")
            except Exception as exc:
                logger.error("Telemetry runtime shutdown failed: %s", exc)


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Configure CORS based on environment
cors_origins = []
if settings.EDGE_ENV == "dev":
    cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "tauri://localhost",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request body size limit
# ---------------------------------------------------------------------------

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose body exceeds MAX_REQUEST_BODY_BYTES."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={"detail": "Request body too large"},
                    )
            except ValueError:
                pass
        return await call_next(request)


# ---------------------------------------------------------------------------
# Request timeout middleware
# ---------------------------------------------------------------------------

class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={"detail": "Request timed out"},
            )


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or request.headers.get("X-Request-ID")
        if not request_id:
            request_id = generate_request_id()
        set_request_id(request_id)
        set_session_id(None)
        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            clear_request_context()


# ---------------------------------------------------------------------------
# Bearer token + rate limiting middleware
# ---------------------------------------------------------------------------

_SKIP_AUTH_PATHS = {
    "/health",
    f"{settings.API_V1_STR}/health",
    f"{settings.API_V1_STR}/",
}
_LOCALHOST_GUARD_EXEMPT_PATHS = set(_SKIP_AUTH_PATHS)


def _is_loopback_host(host: str | None) -> bool:
    """Return True when host is a loopback address/name."""
    if not host:
        return False
    if host.lower() in {"localhost", "testclient"}:
        # "testclient" is Starlette's in-process client host used in unit tests.
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _client_key_from_request(request: Request) -> str:
    """
    Derive an opaque client identifier for rate limiting.

    We use the SHA-256 of the bearer token when present (so we do not
    log the raw token), falling back to the remote IP address.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:]
        return "tok:" + hashlib.sha256(token.encode()).hexdigest()[:16]
    client_host = request.client.host if request.client else "unknown"
    return "ip:" + client_host


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for unprotected paths
        if path in _SKIP_AUTH_PATHS:
            return await call_next(request)
        if path == f"{settings.API_V1_STR}/diagnostics":
            return await call_next(request)

        # Rate limiting (before token verification to block brute force)
        rate_limiter = get_rate_limiter()
        client_key = _client_key_from_request(request)
        allowed, reason = rate_limiter.check(path, client_key)
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": reason},
                headers={"Retry-After": "30"},
            )

        # Verify bearer token
        try:
            await verify_bearer_token(request)
        except HTTPException as exc:
            # Record auth failure for lockout tracking
            rate_limiter.lockout.record_failure(client_key)
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or {},
            )

        # Successful auth; reset lockout counter
        rate_limiter.lockout.record_success(client_key)
        return await call_next(request)


class LocalhostOnlyMiddleware(BaseHTTPMiddleware):
    """
    Defense-in-depth guard: reject requests not originating from localhost.

    The edge API is intended for loopback-only desktop usage.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _LOCALHOST_GUARD_EXEMPT_PATHS:
            return await call_next(request)

        client_host = request.client.host if request.client else None
        if client_host is None and request.headers.get("host", "").startswith("testserver"):
            # Starlette TestClient in-process requests may not populate client scope.
            return await call_next(request)
        if not _is_loopback_host(client_host):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Edge API accepts loopback clients only"},
            )

        return await call_next(request)


# Add middleware (innermost first in execution order with Starlette)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestTimeoutMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LocalhostOnlyMiddleware)
app.add_middleware(BearerTokenMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint (unauthenticated)."""
    return {"status": "ok"}
