"""
Outbox repository for reliable telemetry event delivery.

Implements the outbox pattern with DLQ for handling failed events.
States: PENDING (new/retry), SENT (successful), DLQ (max retries exceeded)
"""
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from .db import get_database


class OutboxEvent:
    """Represents an event in the outbox."""

    def __init__(
        self,
        id: int,
        created_at: str,
        payload_json: str,
        attempts: int,
        next_attempt_at: str,
        status: str,
        last_error: Optional[str] = None,
        last_error_at: Optional[str] = None,
    ):
        self.id = id
        self.created_at = created_at
        self.payload = json.loads(payload_json)
        self.attempts = attempts
        self.next_attempt_at = next_attempt_at
        self.status = status
        self.last_error = last_error
        self.last_error_at = last_error_at


class OutboxRepository:
    """Repository for managing outbox events."""

    def __init__(self, db_path: str = ".sentinelid/audit.db"):
        self.db = get_database(db_path)

    def add_event(self, payload: Dict[str, Any]) -> int:
        """
        Add event to outbox.

        Args:
            payload: Event payload to be delivered

        Returns:
            Event ID in outbox
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        payload_json = json.dumps(payload)
        cursor.execute(
            """
            INSERT INTO outbox_events (payload_json, status)
            VALUES (?, 'PENDING')
            """,
            (payload_json,),
        )
        conn.commit()

        return cursor.lastrowid

    def get_pending_events(self, limit: int = 100) -> List[OutboxEvent]:
        """
        Get events due for delivery.

        Args:
            limit: Maximum number of events to retrieve

        Returns:
            List of pending outbox events
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()
        cursor.execute(
            """
            SELECT id, created_at, payload_json, attempts, next_attempt_at, status,
                   last_error, last_error_at
            FROM outbox_events
            WHERE status = 'PENDING' AND next_attempt_at <= ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (now, limit),
        )

        return [OutboxEvent(*row) for row in cursor.fetchall()]

    def mark_sent(self, event_id: int):
        """
        Mark event as successfully sent.

        Args:
            event_id: ID of the event in outbox
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE outbox_events
            SET status = 'SENT'
            WHERE id = ?
            """,
            (event_id,),
        )
        conn.commit()

    def mark_failed(
        self,
        event_id: int,
        max_attempts: int = 5,
        initial_backoff_seconds: float = 1.0,
    ):
        """
        Mark event as failed and schedule retry.

        Uses exponential backoff with jitter.

        Args:
            event_id: ID of the event in outbox
            max_attempts: Maximum number of retry attempts
            initial_backoff_seconds: Initial backoff duration
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        # Get current event to check attempt count
        cursor.execute(
            """
            SELECT attempts, last_error FROM outbox_events WHERE id = ?
            """,
            (event_id,),
        )
        row = cursor.fetchone()

        if not row:
            return

        attempts, _ = row
        new_attempts = attempts + 1

        if new_attempts >= max_attempts:
            # Move to DLQ
            cursor.execute(
                """
                UPDATE outbox_events
                SET status = 'DLQ', attempts = ?, last_error_at = ?
                WHERE id = ?
                """,
                (new_attempts, datetime.utcnow().isoformat(), event_id),
            )
        else:
            # Schedule retry with exponential backoff
            backoff_seconds = initial_backoff_seconds * (2 ** (new_attempts - 1))
            next_attempt = datetime.utcnow() + timedelta(seconds=backoff_seconds)

            cursor.execute(
                """
                UPDATE outbox_events
                SET attempts = ?, next_attempt_at = ?, last_error_at = ?
                WHERE id = ?
                """,
                (
                    new_attempts,
                    next_attempt.isoformat(),
                    datetime.utcnow().isoformat(),
                    event_id,
                ),
            )

        conn.commit()

    def mark_failed_with_error(
        self,
        event_id: int,
        error: str,
        max_attempts: int = 5,
        initial_backoff_seconds: float = 1.0,
    ):
        """
        Mark event as failed with error message.

        Args:
            event_id: ID of the event in outbox
            error: Error message
            max_attempts: Maximum number of retry attempts
            initial_backoff_seconds: Initial backoff duration
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        # Update error before scheduling retry
        cursor.execute(
            """
            UPDATE outbox_events
            SET last_error = ?
            WHERE id = ?
            """,
            (error, event_id),
        )
        conn.commit()

        # Now schedule retry
        self.mark_failed(event_id, max_attempts, initial_backoff_seconds)

    def get_dlq_events(self, limit: int = 100) -> List[OutboxEvent]:
        """
        Get events in Dead Letter Queue.

        Args:
            limit: Maximum number of events to retrieve

        Returns:
            List of DLQ events
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, created_at, payload_json, attempts, next_attempt_at, status,
                   last_error, last_error_at
            FROM outbox_events
            WHERE status = 'DLQ'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )

        return [OutboxEvent(*row) for row in cursor.fetchall()]

    def replay_dlq_event(self, event_id: int):
        """
        Move event from DLQ back to PENDING for replay.

        Args:
            event_id: ID of the event in DLQ
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE outbox_events
            SET status = 'PENDING', attempts = 0, next_attempt_at = ?, last_error = NULL
            WHERE id = ? AND status = 'DLQ'
            """,
            (datetime.utcnow().isoformat(), event_id),
        )
        conn.commit()

    def get_stats(self) -> Dict[str, int]:
        """
        Get outbox statistics.

        Returns:
            Dictionary with pending_count and dlq_count
        """
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                COUNT(CASE WHEN status = 'PENDING' THEN 1 END) as pending_count,
                COUNT(CASE WHEN status = 'DLQ' THEN 1 END) as dlq_count,
                COUNT(CASE WHEN status = 'SENT' THEN 1 END) as sent_count
            FROM outbox_events
            """
        )

        row = cursor.fetchone()
        return {
            "pending_count": row[0] or 0,
            "dlq_count": row[1] or 0,
            "sent_count": row[2] or 0,
        }
