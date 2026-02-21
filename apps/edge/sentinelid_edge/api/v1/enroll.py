from fastapi import APIRouter
from pydantic import BaseModel
import base64

router = APIRouter()

class Frame(BaseModel):
    frame: str

@router.post("/start")
async def start_enrollment():
    """
    Starts a new enrollment session.
    """
    return {"session_id": "new-enrollment-session"}

@router.post("/frame")
async def enroll_frame(frame: Frame):
    """
    Accepts a base64 encoded image frame for enrollment.
    """
    try:
        # The base64 string is a data URL, like 'data:image/jpeg;base64,....'
        # We need to split it to get the actual base64 data.
        header, data = frame.frame.split(',', 1)
        image_data = base64.b64decode(data)
        return {"status": "frame received", "size": len(image_data)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/commit")
async def commit_enrollment():
    """
    Commits the enrollment after enough frames have been collected.
    """
    return {"status": "enrollment committed"}
