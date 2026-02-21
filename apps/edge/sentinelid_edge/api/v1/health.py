from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_health():
    """
    Health check for the v1 API.
    """
    return {"status": "ok"}
