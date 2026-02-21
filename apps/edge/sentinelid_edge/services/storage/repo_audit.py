"""
Audit log repository with hash-chain integrity.
"""
import json
import uuid
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from .db import get_database
from ..security.crypto import CryptoProvider


@dataclass
class AuditEvent:
    """Audit event with hash-chain fields."""

    event_id: str
    timestamp: int
    event_type: str  # "auth_started", "auth_finished"
    outcome: str  # "allow", "deny", "error"
    reason_codes: List[str]
    similarity_score: Optional[float] = None
    risk_score: Optional[float] = None
    liveness_passed: Optional[bool] = None
    session_id: Optional[str] = None
    prev_hash: Optional[str] = None
    hash: Optional[str] = None


class AuditRepository:
    """Manages audit log storage with append-only hash-chain integrity."""

    def __init__(self, db_path: str = ".sentinelid/audit.db"):
        """
        Initialize audit repository.

        Args:
            db_path: Path to SQLite database
        """
        self.db = get_database(db_path)

    def write_event(self, event: AuditEvent) -> str:
        """
        Write audit event to log with hash-chain validation.

        Args:
            event: Audit event to write

        Returns:
            Event hash

        Raises:
            ValueError: If hash-chain validation fails
        """
        if not event.event_id:
            event.event_id = str(uuid.uuid4())

        if not event.timestamp:
            event.timestamp = int(time.time())

        # Get previous hash for chain
        prev_hash = self._get_last_hash()
        if prev_hash is None:
            prev_hash = "0" * 64  # Genesis block

        event.prev_hash = prev_hash

        # Compute event hash
        event_data = json.dumps({
            'event_id': event.event_id,
            'timestamp': event.timestamp,
            'event_type': event.event_type,
            'outcome': event.outcome,
            'reason_codes': event.reason_codes,
            'similarity_score': event.similarity_score,
            'risk_score': event.risk_score,
            'liveness_passed': event.liveness_passed,
            'session_id': event.session_id,
        }).encode()

        event.hash = CryptoProvider.hash_chain(prev_hash, event_data)

        # Store in database (append-only)
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO audit_events (
                event_id, timestamp, event_type, outcome, reason_codes,
                similarity_score, risk_score, liveness_passed, session_id,
                prev_hash, hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.event_id,
            event.timestamp,
            event.event_type,
            event.outcome,
            json.dumps(event.reason_codes),
            event.similarity_score,
            event.risk_score,
            event.liveness_passed,
            event.session_id,
            event.prev_hash,
            event.hash,
        ))

        conn.commit()
        return event.hash

    def get_events(self, limit: int = 100) -> List[AuditEvent]:
        """
        Retrieve audit events.

        Args:
            limit: Maximum number of events to retrieve

        Returns:
            List of audit events
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM audit_events
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        events = []

        for row in rows:
            event = AuditEvent(
                event_id=row['event_id'],
                timestamp=row['timestamp'],
                event_type=row['event_type'],
                outcome=row['outcome'],
                reason_codes=json.loads(row['reason_codes'] or '[]'),
                similarity_score=row['similarity_score'],
                risk_score=row['risk_score'],
                liveness_passed=bool(row['liveness_passed']) if row['liveness_passed'] is not None else None,
                session_id=row['session_id'],
                prev_hash=row['prev_hash'],
                hash=row['hash'],
            )
            events.append(event)

        return list(reversed(events))  # Return in chronological order

    def verify_chain_integrity(self) -> bool:
        """
        Verify hash-chain integrity of entire audit log.

        Returns:
            True if chain is valid, False otherwise
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT event_id, timestamp, event_type, outcome, reason_codes,
                   similarity_score, risk_score, liveness_passed, session_id,
                   prev_hash, hash
            FROM audit_events
            ORDER BY id ASC
        """)

        rows = cursor.fetchall()
        expected_prev_hash = "0" * 64  # Genesis block

        for row in rows:
            # Verify previous hash matches
            if row['prev_hash'] != expected_prev_hash:
                return False

            # Recompute hash
            event_data = json.dumps({
                'event_id': row['event_id'],
                'timestamp': row['timestamp'],
                'event_type': row['event_type'],
                'outcome': row['outcome'],
                'reason_codes': json.loads(row['reason_codes']),
                'similarity_score': row['similarity_score'],
                'risk_score': row['risk_score'],
                'liveness_passed': row['liveness_passed'],
                'session_id': row['session_id'],
            }).encode()

            computed_hash = CryptoProvider.hash_chain(expected_prev_hash, event_data)

            if computed_hash != row['hash']:
                return False

            expected_prev_hash = row['hash']

        return True

    def _get_last_hash(self) -> Optional[str]:
        """Get the hash of the last audit event."""
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute("SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()

        return row['hash'] if row else None
