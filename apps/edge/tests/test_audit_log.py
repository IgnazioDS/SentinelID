"""
Tests for hash-chained audit log.
"""
import json
import pytest
import time
from sentinelid_edge.services.storage.repo_audit import AuditRepository, AuditEvent
from sentinelid_edge.services.security.crypto import CryptoProvider


class TestAuditLog:
    """Test hash-chained audit log integrity."""

    def test_audit_event_creation(self):
        """Test creating an audit event."""
        event = AuditEvent(
            event_id="test-1",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
            liveness_passed=True,
        )
        assert event.event_id == "test-1"
        assert event.outcome == "allow"
        assert event.liveness_passed is True

    def test_audit_event_write(self, tmp_path):
        """Test writing audit event to repository."""
        db_path = tmp_path / "test_audit.db"
        repo = AuditRepository(str(db_path))

        event = AuditEvent(
            event_id="",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
        )

        hash1 = repo.write_event(event)
        assert hash1 is not None
        assert len(hash1) == 64  # SHA256 hex is 64 chars

    def test_hash_chain_integrity(self, tmp_path):
        """Test hash chain integrity with multiple events."""
        db_path = tmp_path / "test_audit.db"
        repo = AuditRepository(str(db_path))

        # Write first event
        event1 = AuditEvent(
            event_id="",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
        )
        hash1 = repo.write_event(event1)

        # Write second event
        event2 = AuditEvent(
            event_id="",
            timestamp=int(time.time()) + 1,
            event_type="auth_finished",
            outcome="deny",
            reason_codes=["LIVENESS_FAILED"],
        )
        hash2 = repo.write_event(event2)

        # Hashes should be different
        assert hash1 != hash2

        # Chain should be intact
        assert repo.verify_chain_integrity() is True

    def test_chain_integrity_verification(self, tmp_path):
        """Test chain integrity verification method."""
        db_path = tmp_path / "test_audit.db"
        repo = AuditRepository(str(db_path))

        # Write multiple events
        for i in range(5):
            event = AuditEvent(
                event_id="",
                timestamp=int(time.time()) + i,
                event_type="auth_finished",
                outcome="allow" if i % 2 == 0 else "deny",
                reason_codes=["TEST"],
            )
            repo.write_event(event)

        # Verify chain is intact
        assert repo.verify_chain_integrity() is True

    def test_event_retrieval(self, tmp_path):
        """Test retrieving events from repository."""
        db_path = tmp_path / "test_audit.db"
        repo = AuditRepository(str(db_path))

        # Write exactly 3 events
        for i in range(3):
            event = AuditEvent(
                event_id="",
                timestamp=int(time.time()) + i,
                event_type="auth_finished",
                outcome="allow",
                reason_codes=[f"CODE_{i}"],
            )
            repo.write_event(event)

        # Retrieve with limit matching the count
        events = repo.get_events(limit=3)
        assert len(events) == 3, f"Expected 3 events, got {len(events)}"
        assert events[0].reason_codes == ["CODE_0"]
        assert events[2].reason_codes == ["CODE_2"]

    def test_hash_chain_with_data_integrity(self, tmp_path):
        """Test that hash changes if event data is different."""
        db_path = tmp_path / "test_audit.db"
        repo = AuditRepository(str(db_path))

        # Write first event
        event1 = AuditEvent(
            event_id="",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED"],
            similarity_score=0.95,
        )
        hash1 = repo.write_event(event1)

        # Write second event with different data (different outcome)
        event2 = AuditEvent(
            event_id="",  # Different event_id (will be auto-generated)
            timestamp=int(time.time()) + 1,
            event_type="auth_finished",
            outcome="deny",  # Different data
            reason_codes=["LIVENESS_PASSED"],
            similarity_score=0.95,
        )
        hash2 = repo.write_event(event2)

        # Hashes should be different due to different outcome
        assert hash1 != hash2
        assert hash2 is not None

    def test_prev_hash_linkage(self, tmp_path):
        """Test that prev_hash links events together."""
        db_path = tmp_path / "test_audit.db"
        repo = AuditRepository(str(db_path))

        # Write first event
        event1 = AuditEvent(
            event_id="",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["TEST"],
        )
        hash1 = repo.write_event(event1)

        # Write second event
        event2 = AuditEvent(
            event_id="",
            timestamp=int(time.time()) + 1,
            event_type="auth_finished",
            outcome="deny",
            reason_codes=["TEST"],
        )
        repo.write_event(event2)

        # Retrieve events and verify chain
        events = repo.get_events(limit=10)
        assert events[0].hash is not None
        assert events[1].prev_hash == events[0].hash

    def test_audit_payload_encrypted_at_rest(self, tmp_path):
        db_path = tmp_path / "test_audit.db"
        repo = AuditRepository(str(db_path), keychain_dir=str(tmp_path / "keys"))
        event = AuditEvent(
            event_id="",
            timestamp=int(time.time()),
            event_type="auth_finished",
            outcome="allow",
            reason_codes=["LIVENESS_PASSED", "RISK_LOW"],
            similarity_score=0.93,
            risk_score=0.12,
            liveness_passed=True,
            session_id="session-enc-1",
            request_id="req-enc-1",
        )
        repo.write_event(event)

        conn = repo.db.connect()
        row = conn.cursor().execute(
            """
            SELECT reason_codes, similarity_score, risk_score, liveness_passed,
                   session_id, request_id, encrypted_payload
            FROM audit_events
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row["encrypted_payload"] is not None
        assert row["reason_codes"] is None
        assert row["similarity_score"] is None
        assert row["risk_score"] is None
        assert row["liveness_passed"] is None
        assert row["session_id"] is None
        assert row["request_id"] is None
        assert b"LIVENESS_PASSED" not in bytes(row["encrypted_payload"])

    def test_legacy_plaintext_rows_still_verify_and_read(self, tmp_path):
        db_path = tmp_path / "test_audit.db"
        repo = AuditRepository(str(db_path), keychain_dir=str(tmp_path / "keys"))

        payload = {
            "event_id": "legacy-evt-1",
            "timestamp": int(time.time()),
            "event_type": "auth_finished",
            "outcome": "deny",
            "reason_codes": ["LEGACY_REASON"],
            "similarity_score": 0.21,
            "risk_score": 0.81,
            "liveness_passed": False,
            "session_id": "legacy-session-1",
            "request_id": "legacy-request-1",
        }
        prev_hash = "0" * 64
        row_hash = CryptoProvider.hash_chain(prev_hash, json.dumps(payload).encode("utf-8"))

        conn = repo.db.connect()
        conn.cursor().execute(
            """
            INSERT INTO audit_events (
                event_id, timestamp, event_type, outcome, reason_codes,
                similarity_score, risk_score, liveness_passed, session_id, request_id,
                prev_hash, hash, encrypted_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["event_id"],
                payload["timestamp"],
                payload["event_type"],
                payload["outcome"],
                '["LEGACY_REASON"]',
                payload["similarity_score"],
                payload["risk_score"],
                0,
                payload["session_id"],
                payload["request_id"],
                prev_hash,
                row_hash,
                None,
            ),
        )
        conn.commit()

        events = repo.get_events(limit=5)
        assert len(events) == 1
        assert events[0].reason_codes == ["LEGACY_REASON"]
        assert events[0].request_id == "legacy-request-1"
        assert repo.verify_chain_integrity() is True
