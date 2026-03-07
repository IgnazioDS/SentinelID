"""
SentinelID Cloud Ingest Service.

Accepts signed telemetry events from edge devices,
verifies signatures, registers devices, and persists events.
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Add current directory to path to enable absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logging_config import configure_logging
from migrations import run_migrations
from request_context import clear_request_id, generate_request_id, set_request_id
from api.ingest_router import router as ingest_router_router
from api.admin_router import router as admin_router_router

configure_logging(service_name="cloud")
logger = logging.getLogger(__name__)

# Maximum ingest payload size: 5 MB
_MAX_BODY_BYTES = int(os.environ.get("CLOUD_MAX_REQUEST_BODY_BYTES", str(5 * 1024 * 1024)))


# ---------------------------------------------------------------------------
# Request body size limit middleware
# ---------------------------------------------------------------------------

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length exceeds the limit."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > _MAX_BODY_BYTES:
                    logger.warning(
                        "Rejected oversized request: Content-Length=%s path=%s",
                        content_length,
                        request.url.path,
                    )
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={"detail": "Request body too large"},
                    )
            except ValueError:
                pass
        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach and propagate X-Request-Id correlation header."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or request.headers.get("X-Request-ID")
        if not request_id:
            request_id = generate_request_id()
        set_request_id(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            clear_request_id()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("Applying cloud database migrations...")
    run_migrations()
    if not os.environ.get("ADMIN_API_TOKEN"):
        logger.warning("ADMIN_API_TOKEN is not set; admin endpoints will reject requests")
    logger.info("Cloud service ready")
    yield
    logger.info("Cloud service shutting down")


app = FastAPI(
    title="SentinelID Cloud",
    version="2.6.0",
    lifespan=lifespan,
)

app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestIDMiddleware)

# Include routers
app.include_router(ingest_router_router, prefix="/v1")
app.include_router(admin_router_router, prefix="/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("CLOUD_BIND_HOST", "127.0.0.1"), port=8000)
