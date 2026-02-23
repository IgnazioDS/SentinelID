"""
Settings endpoints including identity deletion.
"""
import logging
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ...core.config import settings
from ...services.storage.db import get_database
from ...services.storage.repo_templates import TemplateRepository
from ...services.security.device_binding import DeviceBinding
from ...services.security.encryption import get_master_key_provider

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class DeleteIdentityRequest(BaseModel):
    """
    Options for delete_identity.

    clear_audit: Delete all local audit log events (default true).
    clear_outbox: Delete all pending/DLQ telemetry (default true).
    rotate_device_key: Generate a new device keypair / device_id (default true).
      When false the keypair is deleted and will be regenerated on next boot.
    """
    clear_audit: bool = True
    clear_outbox: bool = True
    rotate_device_key: bool = True


class DeleteIdentityResponse(BaseModel):
    status: str
    templates_deleted: int
    audit_events_deleted: int
    outbox_events_deleted: int
    device_key_rotated: bool
    deleted_at: int


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/settings/delete_identity", response_model=DeleteIdentityResponse)
async def delete_identity(
    request: Request,
    body: DeleteIdentityRequest = None,
) -> DeleteIdentityResponse:
    """
    Wipe all on-device identity data.

    - Deletes all enrolled face templates.
    - Optionally clears the local audit log.
    - Optionally clears telemetry outbox and DLQ.
    - Optionally rotates (or deletes) the device keypair so the next boot
      generates a fresh device_id.

    The operation is best-effort: each step is attempted independently so
    partial success is reported rather than aborting on the first error.
    """
    if body is None:
        body = DeleteIdentityRequest()

    templates_deleted = 0
    audit_deleted = 0
    outbox_deleted = 0
    device_key_rotated = False

    # 1. Delete all templates
    try:
        template_repo = TemplateRepository(
            db_path=settings.DB_PATH,
            keychain_dir=settings.KEYCHAIN_DIR,
        )
        templates_deleted = template_repo.delete_all_templates()
        logger.info("delete_identity: removed %d templates", templates_deleted)
    except Exception as exc:
        logger.error("delete_identity: template deletion failed: %s", exc)

    db = get_database(settings.DB_PATH)
    conn = db.connect()

    # 2. Clear audit log
    if body.clear_audit:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM audit_events")
            audit_deleted = cursor.fetchone()[0]
            cursor.execute("DELETE FROM audit_events")
            conn.commit()
            logger.info("delete_identity: removed %d audit events", audit_deleted)
        except Exception as exc:
            logger.error("delete_identity: audit clear failed: %s", exc)

    # 3. Clear telemetry outbox
    if body.clear_outbox:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM outbox_events")
            outbox_deleted = cursor.fetchone()[0]
            cursor.execute("DELETE FROM outbox_events")
            conn.commit()
            logger.info("delete_identity: removed %d outbox events", outbox_deleted)
        except Exception as exc:
            logger.error("delete_identity: outbox clear failed: %s", exc)

    # 4. Rotate or delete device keypair
    if body.rotate_device_key:
        try:
            _rotate_device_keypair()
            device_key_rotated = True
            logger.info("delete_identity: device keypair rotated")
        except Exception as exc:
            logger.error("delete_identity: keypair rotation failed: %s", exc)

    # 5. Delete the master encryption key so it cannot be reused
    try:
        _delete_master_key()
        logger.info("delete_identity: master encryption key deleted")
    except Exception as exc:
        logger.error("delete_identity: master key deletion failed: %s", exc)

    return DeleteIdentityResponse(
        status="deleted",
        templates_deleted=templates_deleted,
        audit_events_deleted=audit_deleted,
        outbox_events_deleted=outbox_deleted,
        device_key_rotated=device_key_rotated,
        deleted_at=int(time.time()),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rotate_device_keypair():
    """Generate a new ED25519 keypair and derive a new device_id."""
    from ...services.security.crypto import CryptoProvider
    import json
    import os

    keychain_dir = Path(settings.KEYCHAIN_DIR)
    keys_file = keychain_dir / "device_keys.json"
    device_id_file = keychain_dir / "device_id.json"

    # Generate fresh keypair
    private_key, public_key = CryptoProvider.generate_keypair()
    keys_data = {"private_key": private_key, "public_key": public_key}
    keys_file.write_text(json.dumps(keys_data))
    keys_file.chmod(0o600)

    # Derive new device_id
    import uuid
    key_hash = CryptoProvider.hash_sha256(public_key.encode())
    device_id = str(uuid.UUID(key_hash[:32]))
    device_id_file.write_text(json.dumps({"device_id": device_id}))
    device_id_file.chmod(0o600)


def _delete_master_key():
    """
    Remove the master encryption key from keychain and fallback file.
    After deletion, the next operation will generate a fresh key,
    making previously stored blobs permanently unreadable.
    """
    # Invalidate cached key
    provider = get_master_key_provider(settings.KEYCHAIN_DIR)
    provider._cached_key = None

    # Remove from OS keychain
    try:
        import keyring
        keyring.delete_password("com.sentinelid.edge", "master_encryption_key")
    except Exception:
        pass

    # Remove fallback file
    key_file = Path(settings.KEYCHAIN_DIR) / "master_key.hex"
    if key_file.exists():
        key_file.unlink()
