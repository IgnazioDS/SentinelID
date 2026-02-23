"""
Local-only admin endpoints (bearer-protected).

These endpoints perform privileged operations (key rotation) and must
only be reachable from localhost.  Caller must supply the same bearer
token used for the rest of the API.
"""
import logging
import time

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ...services.security.encryption import get_master_key_provider
from ...services.storage.repo_templates import TemplateRepository
from ...core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class KeyRotationResponse(BaseModel):
    status: str
    templates_rewrapped: int
    rotated_at: int


# ---------------------------------------------------------------------------
# Localhost guard
# ---------------------------------------------------------------------------

def _require_localhost(request: Request):
    """Reject requests that do not originate from localhost."""
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only accessible from localhost",
        )


# ---------------------------------------------------------------------------
# Key rotation
# ---------------------------------------------------------------------------

@router.post("/admin/rotate-key", response_model=KeyRotationResponse)
async def rotate_master_key(request: Request) -> KeyRotationResponse:
    """
    Rotate the master encryption key.

    Steps:
    1. Generate a new master key.
    2. Rewrap all template blobs (transactional: all or nothing).
    3. Persist the new master key to the OS keychain / fallback file.

    On any failure the DB is left unchanged (SQLite EXCLUSIVE transaction
    is rolled back) and the old key remains active.

    This endpoint is local-only and bearer-protected (see BearerTokenMiddleware
    in main.py which already guards all /api/v1/* routes).
    """
    _require_localhost(request)

    key_provider = get_master_key_provider(settings.KEYCHAIN_DIR)
    template_repo = TemplateRepository(
        db_path=settings.DB_PATH,
        keychain_dir=settings.KEYCHAIN_DIR,
    )

    try:
        # Generate the new key in memory (do NOT persist yet)
        import secrets
        new_key = secrets.token_bytes(32)

        # Rewrap all blobs atomically; on failure this raises and
        # the old key is still in effect (DB unchanged via rollback)
        rewrapped = template_repo.rewrap_all_blobs(new_key)

        # Rewrap succeeded — now persist the new key and update cache
        key_provider._store_key(new_key)
        key_provider._cached_key = new_key

        logger.info("Key rotation complete: %d templates rewrapped", rewrapped)

        return KeyRotationResponse(
            status="rotated",
            templates_rewrapped=rewrapped,
            rotated_at=int(time.time()),
        )
    except Exception as exc:
        logger.error("Key rotation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Key rotation failed: {exc}",
        )
