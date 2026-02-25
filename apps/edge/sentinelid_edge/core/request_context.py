"""
Request context management with request IDs for tracing.
"""
import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable for storing request ID
_request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
_session_id: ContextVar[Optional[str]] = ContextVar('session_id', default=None)


def set_request_id(request_id: str):
    """Set the current request ID."""
    _request_id.set(request_id)


def get_request_id() -> Optional[str]:
    """Get the current request ID."""
    return _request_id.get()


def set_session_id(session_id: Optional[str]):
    """Set the current session ID for log correlation."""
    _session_id.set(session_id)


def get_session_id() -> Optional[str]:
    """Get the current session ID."""
    return _session_id.get()


def clear_request_context():
    """Clear request-scoped context variables."""
    _request_id.set(None)
    _session_id.set(None)


def generate_request_id() -> str:
    """Generate a new request ID (UUID)."""
    return str(uuid.uuid4())
