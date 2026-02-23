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

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add current directory to path to enable absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import init_db
from api.ingest_router import router as ingest_router_router
from api.admin_router import router as admin_router_router

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


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("Initializing cloud database...")
    init_db()
    logger.info("Cloud service ready")
    yield
    logger.info("Cloud service shutting down")


app = FastAPI(
    title="SentinelID Cloud",
    version="0.6.0",
    lifespan=lifespan,
)

app.add_middleware(RequestSizeLimitMiddleware)

# Include routers
app.include_router(ingest_router_router, prefix="/v1")
app.include_router(admin_router_router, prefix="/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
