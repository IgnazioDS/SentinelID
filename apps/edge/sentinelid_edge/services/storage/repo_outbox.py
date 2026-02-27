"""
Outbox repository for reliable telemetry event delivery.

Implements the outbox pattern with DLQ for handling failed events.
States: PENDING (new/retry), SENT (successful), DLQ (max retries exceeded)
"""
import json
import sqlite3
import random
from datetime import UTC, datetime, timedelta
from typing import List, Optional, Dict, Any
from .db import get_database


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
        last_attempt_at: Optional[str] = None,
        last_success_at: Optional[str] = None,
    ):
        self.id = id
        self.created_at = created_at
        self.payload = json.loads(payload_json)
        self.attempts = attempts
        self.next_attempt_at = next_attempt_at
        self.status = status
        self.last_error = last_error
        self.last_error_at = last_error_at
        self.last_attempt_at = last_attempt_at
        self.last_success_at = last_success_at


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

        now = _utc_now_naive().isoformat()
        cursor.execute(
            """
            SELECT id, created_at, payload_json, attempts, next_attempt_at, status,
                   last_error, last_error_at, last_attempt_at, last_success_at
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
            SET status = 'SENT',
                last_attempt_at = ?,
                last_success_at = ?,
                last_error = NULL,
                last_error_at = NULL
            WHERE id = ?
            """,
            (_utc_now_naive().isoformat(), _utc_now_naive().isoformat(), event_id),
        )
        conn.commit()

    def mark_failed(
        self,
        event_id: int,
        max_attempts: int = 5,
        initial_backoff_seconds: float = 1.0,
        jitter_ratio: float = 0.2,
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
        now_iso = _utc_now_naive().isoformat()

        if new_attempts >= max_attempts:
            # Move to DLQ
            cursor.execute(
                """
                UPDATE outbox_events
                SET status = 'DLQ',
                    attempts = ?,
                    last_error_at = ?,
                    last_attempt_at = ?
                WHERE id = ?
                """,
                (new_attempts, now_iso, now_iso, event_id),
            )
        else:
            # Schedule retry with exponential backoff
            base_backoff_seconds = float(initial_backoff_seconds) * (2 ** (new_attempts - 1))
            jitter = random.uniform(-jitter_ratio, jitter_ratio) if jitter_ratio > 0 else 0.0
            backoff_seconds = max(0.1, base_backoff_seconds * (1.0 + jitter))
            next_attempt = _utc_now_naive() + timedelta(seconds=backoff_seconds)

            cursor.execute(
                """
                UPDATE outbox_events
                SET attempts = ?,
                    next_attempt_at = ?,
                    last_error_at = ?,
                    last_attempt_at = ?
                WHERE id = ?
                """,
                (
                    new_attempts,
                    next_attempt.isoformat(),
                    now_iso,
                    now_iso,
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
        jitter_ratio: float = 0.2,
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
            (_sanitize_error(error), event_id),
        )
        conn.commit()

        # Now schedule retry
        self.mark_failed(event_id, max_attempts, initial_backoff_seconds, jitter_ratio=jitter_ratio)

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
                   last_error, last_error_at, last_attempt_at, last_success_at
            FROM outbox_events
            WHERE status = 'DLQ'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )

        return [OutboxEvent(*row) for row in cursor.fetchall()]

    def replay_dlq_event(self, event_id: int) -> bool:
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
            SET status = 'PENDING',
                attempts = 0,
                next_attempt_at = ?,
                last_error = NULL,
                last_error_at = NULL
            WHERE id = ? AND status = 'DLQ'
            """,
            (_utc_now_naive().isoformat(), event_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def replay_dlq_events(self, limit: int = 100) -> int:
        """
        Move up to limit DLQ events back to PENDING for replay.

        Returns:
            Number of events moved to PENDING
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        now_iso = _utc_now_naive().isoformat()
        cursor.execute(
            """
            UPDATE outbox_events
            SET status = 'PENDING',
                attempts = 0,
                next_attempt_at = ?,
                last_error = NULL,
                last_error_at = NULL
            WHERE id IN (
                SELECT id
                FROM outbox_events
                WHERE status = 'DLQ'
                ORDER BY created_at ASC
                LIMIT ?
            )
            """,
            (now_iso, limit),
        )
        conn.commit()
        return cursor.rowcount

    def get_stats(self) -> Dict[str, Any]:
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
                COUNT(CASE WHEN status = 'SENT' THEN 1 END) as sent_count,
                MAX(last_attempt_at) as last_attempt_at,
                MAX(last_success_at) as last_success_at
            FROM outbox_events
            """
        )

        row = cursor.fetchone()
        cursor.execute(
            """
            SELECT last_error
            FROM outbox_events
            WHERE last_error IS NOT NULL
            ORDER BY COALESCE(last_error_at, created_at) DESC
            LIMIT 1
            """
        )
        last_error_row = cursor.fetchone()
        return {
            "pending_count": row[0] or 0,
            "dlq_count": row[1] or 0,
            "sent_count": row[2] or 0,
            "last_attempt_at": row[3],
            "last_success_at": row[4],
            "last_error_summary": last_error_row[0] if last_error_row else None,
        }


def _sanitize_error(error: str) -> str:
    """Return compact, log-safe error text without multiline content."""
    compact = " ".join(str(error).split())
    return compact[:240]
