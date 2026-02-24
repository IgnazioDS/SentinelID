"""Adaptive frame processing guard for auth sessions."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict

from ...core.config import settings


@dataclass
class _SessionFrameState:
    last_processed_at: float = 0.0
    in_flight: int = 0
    dropped_rate: int = 0
    dropped_backpressure: int = 0
    processed: int = 0
    last_seen_at: float = 0.0


class FrameProcessingController:
    """Caps frame processing rate and drops when processing is already busy."""

    def __init__(
        self,
        max_fps: float = settings.FRAME_PROCESSING_MAX_FPS,
        state_ttl_seconds: int = settings.FRAME_CONTROLLER_STATE_TTL_SECONDS,
    ) -> None:
        self.max_fps = max(1.0, float(max_fps))
        self.min_interval = 1.0 / self.max_fps
        self.state_ttl_seconds = max(30, int(state_ttl_seconds))
        self._lock = threading.Lock()
        self._sessions: Dict[str, _SessionFrameState] = {}
        self._dropped_rate_total = 0
        self._dropped_backpressure_total = 0
        self._processed_total = 0

    def try_acquire(self, session_id: str) -> tuple[bool, str | None]:
        now = time.monotonic()
        with self._lock:
            self._cleanup_locked(now)
            state = self._sessions.setdefault(session_id, _SessionFrameState())
            state.last_seen_at = now
            if state.in_flight > 0:
                state.dropped_backpressure += 1
                self._dropped_backpressure_total += 1
                return False, "queue_backed_up"
            if (now - state.last_processed_at) < self.min_interval:
                state.dropped_rate += 1
                self._dropped_rate_total += 1
                return False, "rate_capped"
            state.in_flight += 1
            return True, None

    def release(self, session_id: str, processed: bool) -> None:
        now = time.monotonic()
        with self._lock:
            state = self._sessions.get(session_id)
            if not state:
                return
            state.in_flight = max(0, state.in_flight - 1)
            state.last_seen_at = now
            if processed:
                state.processed += 1
                state.last_processed_at = now
                self._processed_total += 1

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            self._cleanup_locked(now)
            active = sum(1 for s in self._sessions.values() if s.in_flight > 0)
            sessions = len(self._sessions)
            return {
                "max_fps": self.max_fps,
                "active_sessions": sessions,
                "sessions_in_flight": active,
                "processed_total": self._processed_total,
                "dropped_rate_total": self._dropped_rate_total,
                "dropped_backpressure_total": self._dropped_backpressure_total,
            }

    def _cleanup_locked(self, now: float) -> None:
        expired = [
            session_id
            for session_id, state in self._sessions.items()
            if (now - state.last_seen_at) > self.state_ttl_seconds
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)


_frame_controller = FrameProcessingController()


def get_frame_controller() -> FrameProcessingController:
    return _frame_controller

