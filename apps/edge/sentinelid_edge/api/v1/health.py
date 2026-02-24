from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_health():
    """
    Health check for the v1 API.
    """
    return {"status": "ok"}


@router.get("/health")
async def get_health_detail():
    """Public v1 health endpoint."""
    return {"status": "ok"}
