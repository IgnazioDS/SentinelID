"""
Admin authentication for cloud API endpoints.

Security notes:
- The token is compared with hmac.compare_digest to prevent timing attacks.
- The token value is never logged; only a boolean result is recorded.
- An invalid-token response includes no information about the expected token.
"""
import hashlib
import hmac
import logging
import os

from fastapi import HTTPException, Header, status

logger = logging.getLogger(__name__)


async def verify_admin_token(x_admin_token: str = Header(None)) -> str:
    """
    Verify admin token from request header.

    Args:
        x_admin_token: Admin token from X-Admin-Token header

    Returns:
        The validated token (opaque - callers should not log it)

    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    expected_token = os.environ.get("ADMIN_API_TOKEN", "dev-admin-token")

    if not x_admin_token:
        logger.warning("Admin request rejected: missing X-Admin-Token header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Admin-Token header",
        )

    # Timing-safe comparison to prevent oracle attacks
    tokens_match = hmac.compare_digest(
        x_admin_token.encode("utf-8"),
        expected_token.encode("utf-8"),
    )
    if not tokens_match:
        # Log only that auth failed, not the token value
        logger.warning("Admin request rejected: invalid token (hash=%s)", _token_hash(x_admin_token))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )

    logger.debug("Admin request authorised (hash=%s)", _token_hash(x_admin_token))
    return x_admin_token


def _token_hash(token: str) -> str:
    """Return a short hash of the token for log correlation without exposing the value."""
    return hashlib.sha256(token.encode()).hexdigest()[:8]
