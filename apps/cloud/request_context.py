"""Request-scoped context for cloud logging correlation."""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def get_request_id() -> Optional[str]:
    return _request_id.get()


def clear_request_id() -> None:
    _request_id.set(None)


def generate_request_id() -> str:
    return str(uuid.uuid4())
