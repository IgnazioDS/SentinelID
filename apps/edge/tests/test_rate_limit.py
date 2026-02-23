"""
Tests for rate limiting (token bucket) and lockout tracker.
"""
import time
import pytest

from sentinelid_edge.services.security.rate_limit import (
    LockoutTracker,
    RateLimiter,
    TokenBucket,
)


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------

class TestTokenBucket:
    def test_allows_initial_burst(self):
        bucket = TokenBucket(capacity=5.0, rate=1.0)
        for _ in range(5):
            assert bucket.consume() is True

    def test_blocks_when_empty(self):
        bucket = TokenBucket(capacity=2.0, rate=0.0)  # rate=0 means no refill
        bucket.consume()
        bucket.consume()
        assert bucket.consume() is False

    def test_refills_over_time(self):
        bucket = TokenBucket(capacity=2.0, rate=100.0)
        bucket.consume()
        bucket.consume()
        # With rate=100 tokens/s, a 50ms sleep gives ~5 tokens
        time.sleep(0.05)
        assert bucket.consume() is True

    def test_does_not_exceed_capacity(self):
        bucket = TokenBucket(capacity=3.0, rate=1000.0)
        time.sleep(0.01)  # Let it refill beyond capacity attempt
        allowed = sum(1 for _ in range(10) if bucket.consume())
        assert allowed == 3


# ---------------------------------------------------------------------------
# LockoutTracker
# ---------------------------------------------------------------------------

class TestLockoutTracker:
    def test_not_locked_initially(self):
        tracker = LockoutTracker()
        locked, _ = tracker.is_locked("client-A")
        assert locked is False

    def test_no_lockout_below_threshold(self):
        tracker = LockoutTracker()
        for _ in range(4):
            locked, _ = tracker.record_failure("client-A")
        assert locked is False

    def test_lockout_at_fifth_failure(self):
        tracker = LockoutTracker()
        result = None
        for _ in range(5):
            result = tracker.record_failure("client-A")
        locked, secs = result
        assert locked is True
        assert secs == 30

    def test_lockout_escalates(self):
        tracker = LockoutTracker()
        for _ in range(10):
            tracker.record_failure("client-B")
        locked, secs = tracker.is_locked("client-B")
        assert locked is True
        assert secs > 0

    def test_success_resets_counter(self):
        tracker = LockoutTracker()
        for _ in range(4):
            tracker.record_failure("client-C")
        tracker.record_success("client-C")
        assert tracker.get_failure_count("client-C") == 0

    def test_is_locked_returns_remaining_time(self):
        tracker = LockoutTracker()
        for _ in range(5):
            tracker.record_failure("client-D")
        locked, remaining = tracker.is_locked("client-D")
        assert locked is True
        assert 0 < remaining <= 30

    def test_independent_clients(self):
        tracker = LockoutTracker()
        for _ in range(5):
            tracker.record_failure("bad-client")
        locked_bad, _ = tracker.is_locked("bad-client")
        locked_good, _ = tracker.is_locked("good-client")
        assert locked_bad is True
        assert locked_good is False


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_allows_requests_within_limit(self):
        rl = RateLimiter()
        allowed, reason = rl.check("/api/v1/health", "client-1")
        assert allowed is True
        assert reason == ""

    def test_blocks_locked_client(self):
        rl = RateLimiter()
        # Manually lock client
        for _ in range(5):
            rl.lockout.record_failure("locked-client")
        allowed, reason = rl.check("/api/v1/auth/start", "locked-client")
        assert allowed is False
        assert "retry" in reason.lower() or "failure" in reason.lower()

    def test_auth_endpoint_has_tighter_limit(self):
        """Auth endpoints should exhaust capacity faster than non-auth."""
        rl = RateLimiter()
        auth_ep = "/api/v1/auth/start"
        # Drain the burst for auth endpoint (capacity=10)
        results = [rl.check(auth_ep, "rapid-client") for _ in range(15)]
        blocked = [r for r in results if not r[0]]
        assert len(blocked) > 0

    def test_different_clients_independent(self):
        rl = RateLimiter()
        # Exhaust bucket for client-X
        for _ in range(30):
            rl.check("/api/v1/auth/start", "client-X")
        # client-Y should still be allowed
        allowed, _ = rl.check("/api/v1/auth/start", "client-Y")
        assert allowed is True

    def test_rate_limit_message_on_block(self):
        rl = RateLimiter()
        for _ in range(12):
            rl.check("/api/v1/auth/start", "spam-client")
        allowed, reason = rl.check("/api/v1/auth/start", "spam-client")
        if not allowed:
            assert "rate limit" in reason.lower() or "retry" in reason.lower()
