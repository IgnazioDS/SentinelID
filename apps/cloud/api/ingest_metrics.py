"""In-memory ingest reliability counters for admin observability."""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class IngestMetrics:
    success_timestamps: deque[float] = field(default_factory=deque)
    failure_timestamps: deque[float] = field(default_factory=deque)
    events_ingested_count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_success(self, events_ingested: int) -> None:
        now = time.time()
        with self._lock:
            self.success_timestamps.append(now)
            self.events_ingested_count += max(0, int(events_ingested))

    def record_failure(self) -> None:
        now = time.time()
        with self._lock:
            self.failure_timestamps.append(now)

    def snapshot(self, window_seconds: int = 3600) -> dict:
        now = time.time()
        cutoff = now - max(1, int(window_seconds))
        with self._lock:
            while self.success_timestamps and self.success_timestamps[0] < cutoff:
                self.success_timestamps.popleft()
            while self.failure_timestamps and self.failure_timestamps[0] < cutoff:
                self.failure_timestamps.popleft()
            return {
                "ingest_success_count": len(self.success_timestamps),
                "ingest_fail_count": len(self.failure_timestamps),
                "events_ingested_count": int(self.events_ingested_count),
                "ingest_window_seconds": int(window_seconds),
            }


_ingest_metrics = IngestMetrics()


def get_ingest_metrics() -> IngestMetrics:
    return _ingest_metrics
