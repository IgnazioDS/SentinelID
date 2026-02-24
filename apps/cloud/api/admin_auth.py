"""Admin authentication for cloud API endpoints."""
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
    expected_token = os.environ.get("ADMIN_API_TOKEN")
    if not expected_token:
        logger.error("Admin API token is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API token not configured",
        )

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
        logger.warning("Admin request rejected: invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )

    logger.debug("Admin request authorised")
    return x_admin_token
