"""
Request context management with request IDs for tracing.
"""
import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable for storing request ID
_request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


def set_request_id(request_id: str):
    """Set the current request ID."""
    _request_id.set(request_id)


def get_request_id() -> Optional[str]:
    """Get the current request ID."""
    return _request_id.get()


def generate_request_id() -> str:
    """Generate a new request ID (UUID)."""
    return str(uuid.uuid4())
