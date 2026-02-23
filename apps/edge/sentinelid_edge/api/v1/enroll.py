"""
Enrollment endpoints.

Enrollment stores an encrypted face embedding so subsequent auth sessions
can verify identity against it.  The embedding is stored via TemplateRepository
which encrypts it with AES-256-GCM before writing to SQLite.
"""
import base64
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from ...core.config import settings
from ...services.storage.repo_templates import TemplateRepository

logger = logging.getLogger(__name__)
router = APIRouter()

_template_repo: Optional[TemplateRepository] = None


def _get_template_repo() -> TemplateRepository:
    global _template_repo
    if _template_repo is None:
        _template_repo = TemplateRepository(
            db_path=settings.DB_PATH,
            keychain_dir=settings.KEYCHAIN_DIR,
        )
    return _template_repo


class EnrollFrameRequest(BaseModel):
    frame: str  # base64-encoded image


class EnrollCommitRequest(BaseModel):
    label: str = "default"


@router.post("/start")
async def start_enrollment():
    """Start a new enrollment session."""
    return {"session_id": "new-enrollment-session"}


@router.post("/frame")
async def enroll_frame(request: EnrollFrameRequest):
    """
    Accept a base64-encoded frame for enrollment.

    In a full implementation this would extract and accumulate an embedding.
    The frame bytes are not stored; only the derived embedding will be
    persisted (encrypted) at commit time.
    """
    try:
        if "," in request.frame:
            _, data = request.frame.split(",", 1)
        else:
            data = request.frame
        image_data = base64.b64decode(data)
        return {"status": "frame received", "size": len(image_data)}
    except Exception as exc:
        logger.warning("enroll_frame error: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid frame data",
        )


@router.post("/commit")
async def commit_enrollment(request: EnrollCommitRequest):
    """
    Commit enrollment by storing an encrypted template.

    In a full implementation the embedding extracted from frames would be
    stored here.  This stub stores a placeholder and returns the template_id.
    """
    import numpy as np
    # Placeholder: in production this would be the embedding averaged from
    # the enrollment frames collected in /enroll/frame calls.
    placeholder_embedding = np.zeros(512, dtype=np.float32)
    try:
        repo = _get_template_repo()
        template_id = repo.store_template(request.label, placeholder_embedding)
        logger.info("Enrollment committed: label=%s template_id=%s", request.label, template_id)
        return {"status": "enrollment committed", "template_id": template_id}
    except Exception as exc:
        logger.error("Enrollment commit failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Enrollment commit failed",
        )
