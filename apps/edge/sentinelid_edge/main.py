import hashlib
import logging

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from sentinelid_edge.api.router import api_router
from sentinelid_edge.core.config import settings
from sentinelid_edge.core.auth import verify_bearer_token
from sentinelid_edge.core.request_context import set_request_id, generate_request_id
from sentinelid_edge.services.security.rate_limit import get_rate_limiter

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
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
# Request ID middleware
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = generate_request_id()
        set_request_id(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Bearer token + rate limiting middleware
# ---------------------------------------------------------------------------

_SKIP_AUTH_PATHS = {
    "/health",
}
_SKIP_AUTH_PREFIXES = (
    f"{settings.API_V1_STR}/",   # root v1 path (health)
    f"{settings.API_V1_STR}/diagnostics",
)


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
        if path == f"{settings.API_V1_STR}/" or path == f"{settings.API_V1_STR}/diagnostics":
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


# Add middleware (innermost first in execution order with Starlette)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(BearerTokenMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint (unauthenticated)."""
    return {"status": "ok"}
