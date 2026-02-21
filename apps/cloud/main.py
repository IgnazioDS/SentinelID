"""
SentinelID Cloud Ingest Service.

Accepts signed telemetry events from edge devices,
verifies signatures, registers devices, and persists events.
"""
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database initialization
# Use absolute imports to work with uvicorn
import sys
import os
# Add current directory to path to enable absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import init_db
from api.ingest_router import router as ingest_router_router
from api.admin_router import router as admin_router_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    logger.info("Initializing cloud database...")
    init_db()
    logger.info("Cloud service ready")
    yield
    # Shutdown
    logger.info("Cloud service shutting down")


app = FastAPI(
    title="SentinelID Cloud",
    version="0.3.0",
    lifespan=lifespan
)

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
