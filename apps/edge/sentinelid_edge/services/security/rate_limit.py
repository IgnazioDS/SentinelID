"""
Rate limiting and lockout for edge API endpoints.

Design:
  - Token bucket per (endpoint, client_key) where client_key is derived
    from the bearer token or remote IP.
  - Failure counter per client_key with escalating lockout durations.
  - All state is in-process; suitable for single-process edge deployment.
  - Thread-safe via a simple threading.Lock.

Lockout schedule (doubles on each successive lockout):
  failure #1-4  : no lockout
  failure #5    : 30 s lockout
  failure #10   : 60 s
  failure #20   : 120 s
  failure #40+  : 300 s (max)
"""
import threading
import time
import logging
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

    def __init__(self):
        # {client_key: {"failures": int, "locked_until": float}}
        self._state: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def is_locked(self, client_key: str) -> Tuple[bool, float]:
        """
        Check if a client is currently locked out.

        Returns:
            (is_locked, seconds_remaining)
        """
        with self._lock:
            state = self._state.get(client_key)
            if state is None:
                return False, 0.0
            locked_until = state.get("locked_until", 0.0)
            now = time.monotonic()
            if locked_until > now:
                return True, locked_until - now
            return False, 0.0

    def record_failure(self, client_key: str) -> Tuple[bool, float]:
        """
        Record an authentication failure and apply lockout if threshold reached.

        Returns:
            (is_now_locked, lockout_seconds)
        """
        with self._lock:
            state = self._state.setdefault(client_key, {"failures": 0, "locked_until": 0.0})
            state["failures"] += 1
            failures = state["failures"]

        lockout_secs = self._lockout_for_failures(failures)
        if lockout_secs > 0:
            with self._lock:
                self._state[client_key]["locked_until"] = time.monotonic() + lockout_secs
            logger.warning(
                "Client %s locked out for %ds after %d failures",
                client_key,
                lockout_secs,
                failures,
            )
            return True, lockout_secs
        return False, 0.0

    def record_success(self, client_key: str):
        """Reset failure counter on successful authentication."""
        with self._lock:
            if client_key in self._state:
                self._state[client_key]["failures"] = 0
                self._state[client_key]["locked_until"] = 0.0

    def get_failure_count(self, client_key: str) -> int:
        with self._lock:
            return self._state.get(client_key, {}).get("failures", 0)

    @staticmethod
    def _lockout_for_failures(failures: int) -> int:
        for min_failures, lockout_secs in _LOCKOUT_SCHEDULE:
            if failures >= min_failures:
                return lockout_secs
        return 0


# ---------------------------------------------------------------------------
# Per-endpoint rate limiter registry
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Registry of per-(endpoint, client) token buckets.

    Default configuration:
      - auth endpoints: 10 req/s burst, 2 req/s sustained
      - other endpoints: 30 req/s burst, 10 req/s sustained
    """

    _AUTH_CAPACITY = 10.0
    _AUTH_RATE = 2.0
    _DEFAULT_CAPACITY = 30.0
    _DEFAULT_RATE = 10.0
    _AUTH_ENDPOINTS = {"/api/v1/auth/start", "/api/v1/auth/frame", "/api/v1/auth/finish"}

    def __init__(self):
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self.lockout = LockoutTracker()

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
                if endpoint in self._AUTH_ENDPOINTS:
                    self._buckets[bucket_key] = TokenBucket(
                        self._AUTH_CAPACITY, self._AUTH_RATE
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
        _rate_limiter = RateLimiter()
    return _rate_limiter
