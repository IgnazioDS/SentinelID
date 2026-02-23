from fastapi import APIRouter
from sentinelid_edge.api.v1 import health, enroll, auth, settings, admin

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(enroll.router, prefix="/enroll", tags=["enroll"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(admin.router, tags=["admin"])
