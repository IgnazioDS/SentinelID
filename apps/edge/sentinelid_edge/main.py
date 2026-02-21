from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sentinelid_edge.api.router import api_router
from sentinelid_edge.core.config import settings
from sentinelid_edge.core.auth import verify_bearer_token

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
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


# Bearer token middleware (except /api/v1/health)
class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health endpoint
        if request.url.path == f"{settings.API_V1_STR}/":
            return await call_next(request)

        # Verify token for all other routes
        try:
            await verify_bearer_token(request)
        except HTTPException as exc:
            # Convert HTTPException to proper JSONResponse
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )

        return await call_next(request)


app.add_middleware(BearerTokenMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint (unauthenticated).
    """
    return {"status": "ok"}
