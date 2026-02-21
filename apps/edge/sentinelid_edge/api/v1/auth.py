from fastapi import APIRouter, UploadFile, File

router = APIRouter()

@router.post("/start")
async def start_authentication():
    """
    Starts an authentication session and returns challenges.
    """
    return {"session_id": "new-auth-session", "challenges": ["blink", "turn_head_left"]}

@router.post("/frame")
async def auth_frame(file: UploadFile = File(...)):
    """
    Accepts an image frame for authentication and returns partial state.
    """
    return {"status": "frame received", "filename": file.filename, "challenge_status": "pending"}

@router.post("/finish")
async def finish_authentication():
    """
    Finishes the authentication session and returns a decision.
    """
    # This will be replaced with real logic from the policy engine.
    return {"decision": "allow", "reason": "all checks passed"}
