"""
Admin authentication for cloud API endpoints.
"""
import os
from fastapi import HTTPException, Header, status


async def verify_admin_token(x_admin_token: str = Header(None)):
    """
    Verify admin token from request header.

    Args:
        x_admin_token: Admin token from X-Admin-Token header

    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    expected_token = os.environ.get("ADMIN_API_TOKEN", "dev-admin-token")

    if not x_admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Admin-Token header"
        )

    if x_admin_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token"
        )

    return x_admin_token
