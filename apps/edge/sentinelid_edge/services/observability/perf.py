"""In-process stage timing metrics with rolling p50/p95 snapshots."""
from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Deque, Dict, Iterator, List

from ...core.config import settings


class PerfRegistry:
    """Collects stage durations in a bounded rolling window."""

    def __init__(self, window_size: int = settings.PERF_WINDOW_SIZE) -> None:
        self.window_size = max(10, int(window_size))
        self._lock = threading.Lock()
        self._durations: Dict[str, Deque[float]] = {}
        self._totals: Dict[str, float] = {}
        self._counts: Dict[str, int] = {}

    def observe_ms(self, stage: str, duration_ms: float) -> None:
        d = max(0.0, float(duration_ms))
        with self._lock:
            window = self._durations.setdefault(stage, deque(maxlen=self.window_size))
            window.append(d)
            self._totals[stage] = self._totals.get(stage, 0.0) + d
            self._counts[stage] = self._counts.get(stage, 0) + 1

    @contextmanager
    def stage(self, stage: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe_ms(stage, (time.perf_counter() - started) * 1000.0)

    def snapshot(self) -> Dict[str, Dict[str, float | int | None]]:
        with self._lock:
            result: Dict[str, Dict[str, float | int | None]] = {}
            for stage, values in self._durations.items():
                ordered: List[float] = sorted(values)
                count = self._counts.get(stage, 0)
                total = self._totals.get(stage, 0.0)
                result[stage] = {
                    "count": count,
                    "mean_ms": round((total / count), 3) if count else None,
                    "p50_ms": round(_percentile(ordered, 50), 3) if ordered else None,
                    "p95_ms": round(_percentile(ordered, 95), 3) if ordered else None,
                    "max_ms": round(max(ordered), 3) if ordered else None,
                    "window_count": len(ordered),
                }
            return result


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    idx = (len(values) - 1) * (percentile / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    if lo == hi:
        return values[lo]
    frac = idx - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


_perf_registry = PerfRegistry()


def get_perf_registry() -> PerfRegistry:
    return _perf_registry

