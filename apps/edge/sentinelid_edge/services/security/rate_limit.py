"""
Rate limiting and lockout for edge API endpoints.

Design:
  - Token bucket per (endpoint, client_key) where client_key is derived
    from the bearer token or remote IP.
  - Failure counter per client_key with escalating lockout durations.
  - Lockout state is persisted locally so restart does not clear abuse history.
  - Thread-safe via a simple threading.Lock.

Lockout schedule (doubles on each successive lockout):
  failure #1-4  : no lockout
  failure #5    : 30 s lockout
  failure #10   : 60 s
  failure #20   : 120 s
  failure #40+  : 300 s (max)
"""

import logging
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token bucket implementation
# ---------------------------------------------------------------------------

class TokenBucket:
    """
    Classic token bucket for rate limiting.

    Tokens are added at `rate` tokens/second up to `capacity`.
    A request consumes one token; if the bucket is empty the request is denied.
    """

    __slots__ = ("capacity", "rate", "_tokens", "_last_refill", "_lock")

    def __init__(self, capacity: float, rate: float):
        """
        Args:
            capacity: Maximum number of tokens (burst size)
            rate: Token refill rate in tokens/second
        """
        self.capacity = capacity
        self.rate = rate
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> bool:
        """
        Attempt to consume tokens from the bucket.

        Returns:
            True if the request is allowed, False if rate-limited
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self.capacity,
                self._tokens + elapsed * self.rate,
            )
            self._last_refill = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


# ---------------------------------------------------------------------------
# Lockout tracker
# ---------------------------------------------------------------------------

_LOCKOUT_SCHEDULE: Tuple[Tuple[int, int], ...] = (
    # (min_failures, lockout_seconds)
    (40, 300),
    (20, 120),
    (10, 60),
    (5, 30),
)


class LockoutTracker:
    """
    Tracks consecutive authentication failures per client key and enforces
    escalating lockout durations.
    """

    def __init__(self, state_path: Optional[str] = None):
        # {client_key: {"failures": int, "locked_until_epoch": float, "updated_at_epoch": float}}
        self._state: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._state_path = Path(state_path) if state_path else None
        if self._state_path:
            try:
                self._state_path.parent.mkdir(parents=True, exist_ok=True)
                self._load_state()
            except Exception as exc:
                logger.warning(
                    "Disabling lockout persistence for %s: %s", self._state_path, exc
                )
                self._state_path = None

    def is_locked(self, client_key: str) -> Tuple[bool, float]:
        """
        Check if a client is currently locked out.

        Returns:
            (is_locked, seconds_remaining)
        """
        changed = False
        with self._lock:
            state = self._state.get(client_key)
            if state is None:
                return False, 0.0
            locked_until = float(state.get("locked_until_epoch", 0.0))
            now = time.time()
            if locked_until > now:
                return True, locked_until - now
            if locked_until != 0.0:
                state["locked_until_epoch"] = 0.0
                state["updated_at_epoch"] = now
                changed = True
        if changed:
            self._persist_state()
        return False, 0.0

    def record_failure(self, client_key: str) -> Tuple[bool, float]:
        """
        Record an authentication failure and apply lockout if threshold reached.

        Returns:
            (is_now_locked, lockout_seconds)
        """
        changed = False
        with self._lock:
            now = time.time()
            state = self._state.setdefault(
                client_key,
                {"failures": 0, "locked_until_epoch": 0.0, "updated_at_epoch": now},
            )
            state["failures"] = int(state.get("failures", 0)) + 1
            state["updated_at_epoch"] = now
            failures = state["failures"]
            lockout_secs = self._lockout_for_failures(failures)
            if lockout_secs > 0:
                state["locked_until_epoch"] = now + lockout_secs
                logger.warning(
                    "Client %s locked out for %ds after %d failures",
                    client_key,
                    lockout_secs,
                    failures,
                )
                changed = True
            else:
                changed = True
        if changed:
            self._persist_state()
        if lockout_secs > 0:
            return True, float(lockout_secs)
        return False, 0.0

    def record_success(self, client_key: str):
        """Reset failure counter on successful authentication."""
        changed = False
        with self._lock:
            if client_key in self._state:
                del self._state[client_key]
                changed = True
        if changed:
            self._persist_state()

    def get_failure_count(self, client_key: str) -> int:
        with self._lock:
            return int(self._state.get(client_key, {}).get("failures", 0))

    @staticmethod
    def _lockout_for_failures(failures: int) -> int:
        for min_failures, lockout_secs in _LOCKOUT_SCHEDULE:
            if failures >= min_failures:
                return lockout_secs
        return 0

    def _load_state(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        try:
            with self._state_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            raw_clients = payload.get("clients", {}) if isinstance(payload, dict) else {}
            if not isinstance(raw_clients, dict):
                return
            now = time.time()
            loaded: Dict[str, Dict] = {}
            for client_key, raw in raw_clients.items():
                if not isinstance(client_key, str) or not isinstance(raw, dict):
                    continue
                failures = int(raw.get("failures", 0))
                locked_until = float(
                    raw.get("locked_until_epoch", raw.get("locked_until", 0.0))
                )
                updated_at = float(raw.get("updated_at_epoch", now))
                if failures <= 0 and locked_until <= now:
                    continue
                loaded[client_key] = {
                    "failures": max(failures, 0),
                    "locked_until_epoch": max(locked_until, 0.0),
                    "updated_at_epoch": max(updated_at, 0.0),
                }
            with self._lock:
                self._state = loaded
        except Exception as exc:
            logger.warning("Failed to load lockout state from %s: %s", self._state_path, exc)

    def _persist_state(self) -> None:
        if self._state_path is None:
            return
        try:
            with self._lock:
                self._persist_state_locked()
        except Exception as exc:
            logger.warning("Failed to persist lockout state to %s: %s", self._state_path, exc)

    def _persist_state_locked(self) -> None:
        if self._state_path is None:
            return
        now = time.time()
        clients: Dict[str, Dict] = {}
        for client_key, state in self._state.items():
            failures = int(state.get("failures", 0))
            locked_until = float(state.get("locked_until_epoch", 0.0))
            updated_at = float(state.get("updated_at_epoch", now))
            if failures <= 0 and locked_until <= now:
                continue
            clients[client_key] = {
                "failures": max(failures, 0),
                "locked_until_epoch": max(locked_until, 0.0),
                "updated_at_epoch": max(updated_at, 0.0),
            }

        payload = {
            "version": 1,
            "updated_at_epoch": now,
            "clients": clients,
        }
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".lockout_state.", suffix=".tmp", dir=str(self._state_path.parent)
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            os.replace(tmp_path, self._state_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Per-endpoint rate limiter registry
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Registry of per-(endpoint, client) token buckets.

    Default configuration:
      - auth start/finish endpoints: 10 req burst, 2 req/s sustained
      - auth frame endpoint (streaming): 20 req burst, 12 req/s sustained
      - other endpoints: 30 req burst, 10 req/s sustained
    """

    _AUTH_MUTATION_CAPACITY = 10.0
    _AUTH_MUTATION_RATE = 2.0
    _AUTH_FRAME_CAPACITY = 20.0
    _AUTH_FRAME_RATE = 12.0
    _DEFAULT_CAPACITY = 30.0
    _DEFAULT_RATE = 10.0
    _AUTH_MUTATION_ENDPOINTS = {"/api/v1/auth/start", "/api/v1/auth/finish"}
    _AUTH_FRAME_ENDPOINTS = {"/api/v1/auth/frame"}

    def __init__(self, lockout_state_path: Optional[str] = None):
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self.lockout = LockoutTracker(state_path=lockout_state_path)

    def check(self, endpoint: str, client_key: str) -> Tuple[bool, str]:
        """
        Check whether the request is allowed.

        Args:
            endpoint: Request path (e.g. "/api/v1/auth/start")
            client_key: Identifier for the client (e.g. hashed token or IP)

        Returns:
            (allowed, reason)  where reason is "" if allowed
        """
        # Check lockout first
        locked, remaining = self.lockout.is_locked(client_key)
        if locked:
            return False, f"Too many failures; retry after {remaining:.0f}s"

        # Check token bucket
        bucket_key = f"{endpoint}:{client_key}"
        bucket = self._get_or_create_bucket(bucket_key, endpoint)
        if not bucket.consume():
            return False, "Rate limit exceeded"

        return True, ""

    def _get_or_create_bucket(self, bucket_key: str, endpoint: str) -> TokenBucket:
        with self._lock:
            if bucket_key not in self._buckets:
                if endpoint in self._AUTH_FRAME_ENDPOINTS:
                    self._buckets[bucket_key] = TokenBucket(
                        self._AUTH_FRAME_CAPACITY, self._AUTH_FRAME_RATE
                    )
                elif endpoint in self._AUTH_MUTATION_ENDPOINTS:
                    self._buckets[bucket_key] = TokenBucket(
                        self._AUTH_MUTATION_CAPACITY, self._AUTH_MUTATION_RATE
                    )
                else:
                    self._buckets[bucket_key] = TokenBucket(
                        self._DEFAULT_CAPACITY, self._DEFAULT_RATE
                    )
            return self._buckets[bucket_key]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Return the module-level RateLimiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        from sentinelid_edge.core.config import settings

        _rate_limiter = RateLimiter(lockout_state_path=settings.LOCKOUT_STATE_PATH)
    return _rate_limiter
