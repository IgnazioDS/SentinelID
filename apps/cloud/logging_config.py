"""Structured logging configuration for cloud service."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from request_context import get_request_id

_SECRET_KEY_PATTERN = re.compile(
    r"(?i)\b(authorization|token|x-admin-token|edge_auth_token|signature|batch_signature)\b"
)
_BEARER_PATTERN = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9\-._~+/]+=*")


def _sanitize_text(value: str) -> str:
    return _BEARER_PATTERN.sub(r"\1[REDACTED]", str(value))


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _SECRET_KEY_PATTERN.search(str(key)):
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = _sanitize_value(item)
        return out
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item) for item in value)
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


class _ContextFilter(logging.Filter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = getattr(record, "service", self._service)
        record.request_id = getattr(record, "request_id", None) or get_request_id()
        record.session_id = getattr(record, "session_id", None)
        record.device_id = getattr(record, "device_id", None)
        record.event_id = getattr(record, "event_id", None)
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "service": getattr(record, "service", "cloud"),
            "request_id": getattr(record, "request_id", None),
            "session_id": getattr(record, "session_id", None),
            "device_id": getattr(record, "device_id", None),
            "event_id": getattr(record, "event_id", None),
            "logger": record.name,
            "msg": _sanitize_text(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(_sanitize_value(payload), ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, timezone.utc).isoformat()
        fields = [
            f"ts={ts}",
            f"level={record.levelname.lower()}",
            f"service={getattr(record, 'service', 'cloud')}",
            f"request_id={getattr(record, 'request_id', '-') or '-'}",
            f"session_id={getattr(record, 'session_id', '-') or '-'}",
            f"device_id={getattr(record, 'device_id', '-') or '-'}",
            f"event_id={getattr(record, 'event_id', '-') or '-'}",
            f"logger={record.name}",
            f"msg={_sanitize_text(record.getMessage())}",
        ]
        if record.exc_info:
            fields.append(f"exc={self.formatException(record.exc_info)}")
        return " ".join(fields)


def configure_logging(service_name: str = "cloud") -> None:
    resolved_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    resolved_format = os.environ.get("LOG_FORMAT", "text").strip().lower()
    formatter: logging.Formatter = _JsonFormatter() if resolved_format == "json" else _TextFormatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(_ContextFilter(service_name))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, resolved_level, logging.INFO))

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        target = logging.getLogger(logger_name)
        target.handlers.clear()
        target.propagate = True
