"""Background telemetry export runtime with graceful shutdown."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ...core.config import settings
from ..observability.perf import get_perf_registry
from .event import TelemetryEvent
from .exporter import TelemetryExporter

logger = logging.getLogger(__name__)


@dataclass
class TelemetryRuntimeStats:
    loop_started_at: float = field(default_factory=time.time)
    loop_iterations: int = 0
    export_errors: int = 0
    dropped_signals: int = 0
    wake_signals: int = 0
    last_loop_error: Optional[str] = None
    last_export_success_at: Optional[float] = None


class TelemetryRuntime:
    """Owns exporter background loop and bounded wake-up queue."""

    def __init__(
        self,
        exporter: TelemetryExporter,
        export_interval_seconds: float = settings.TELEMETRY_EXPORT_INTERVAL_SECONDS,
        signal_queue_size: int = settings.TELEMETRY_SIGNAL_QUEUE_SIZE,
    ) -> None:
        self.exporter = exporter
        self.enabled = settings.TELEMETRY_ENABLED
        self.export_interval_seconds = max(0.2, float(export_interval_seconds))
        self._signals: asyncio.Queue[str] = asyncio.Queue(maxsize=max(8, int(signal_queue_size)))
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._stats = TelemetryRuntimeStats()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="sentinelid-telemetry-exporter")

    async def stop(self) -> None:
        self._stop_event.set()
        self._signal("shutdown")
        if self._task is not None:
            await self._task
            self._task = None
        # Final forced flush as part of graceful shutdown.
        with get_perf_registry().stage("exporter.flush_shutdown"):
            await self.exporter.flush()

    def record_event(self, event: TelemetryEvent) -> None:
        if not self.enabled:
            return
        self.exporter.add_event(event)
        self._signal("event")

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self._signal("toggle")

    def _signal(self, signal: str) -> None:
        try:
            self._signals.put_nowait(signal)
            self._stats.wake_signals += 1
        except asyncio.QueueFull:
            self._stats.dropped_signals += 1

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._signals.get(),
                    timeout=self.export_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

            self._stats.loop_iterations += 1
            if not self.enabled:
                continue
            try:
                with get_perf_registry().stage("exporter.batch"):
                    success = await self.exporter.export_pending(force=False)
                if success:
                    self._stats.last_export_success_at = time.time()
            except Exception as exc:
                self._stats.export_errors += 1
                self._stats.last_loop_error = str(exc)
                logger.error("Telemetry background export failed: %s", exc)

    def stats(self) -> dict:
        exporter_stats = self.exporter.get_stats()
        return {
            "enabled": self.enabled,
            "queue": {
                "max_size": self._signals.maxsize,
                "current_size": self._signals.qsize(),
                "wake_signals": self._stats.wake_signals,
                "dropped_signals": self._stats.dropped_signals,
            },
            "loop": {
                "started_at": self._stats.loop_started_at,
                "iterations": self._stats.loop_iterations,
                "export_errors": self._stats.export_errors,
                "last_loop_error": self._stats.last_loop_error,
                "last_export_success_at": self._stats.last_export_success_at,
            },
            "outbox": {
                "pending_count": exporter_stats["pending_count"],
                "dlq_count": exporter_stats["dlq_count"],
                "sent_count": exporter_stats["sent_count"],
            },
            "last_export_attempt_time": exporter_stats["last_export_attempt_time"],
            "last_export_success_time": exporter_stats.get("last_export_success_time"),
            "last_export_error": exporter_stats["last_export_error"],
        }


_runtime: Optional[TelemetryRuntime] = None


def set_telemetry_runtime(runtime: Optional[TelemetryRuntime]) -> None:
    global _runtime
    _runtime = runtime


def get_telemetry_runtime() -> Optional[TelemetryRuntime]:
    return _runtime
