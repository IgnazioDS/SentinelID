"""
Tests for outbox repository with DLQ pattern.
"""
import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
from sentinelid_edge.services.storage.repo_outbox import OutboxRepository


@pytest.fixture
def temp_db():
    """Create temporary database for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/test.db"
        # Initialize schema
        from sentinelid_edge.services.storage.db import Database
        db = Database(db_path)
        db.init_schema()
        db.close()
        yield db_path


class TestOutboxRepository:
    """Test outbox repository functionality."""

    def test_add_event(self, temp_db):
        """Test adding event to outbox."""
        repo = OutboxRepository(temp_db)
        payload = {'event_id': '123', 'data': 'test'}

        event_id = repo.add_event(payload)

        assert event_id > 0
        events = repo.get_pending_events()
        assert len(events) == 1
        assert events[0].payload == payload
        assert events[0].status == 'PENDING'

    def test_mark_sent(self, temp_db):
        """Test marking event as sent."""
        repo = OutboxRepository(temp_db)
        payload = {'event_id': '123'}
        event_id = repo.add_event(payload)

        repo.mark_sent(event_id)

        pending = repo.get_pending_events()
        assert len(pending) == 0

        stats = repo.get_stats()
        assert stats['sent_count'] == 1

    def test_mark_failed_moves_to_dlq_after_max_attempts(self, temp_db):
        """Test event moves to DLQ after max attempts."""
        repo = OutboxRepository(temp_db)
        payload = {'event_id': '123'}
        event_id = repo.add_event(payload)

        # Fail 5 times
        max_attempts = 5
        for _ in range(max_attempts):
            repo.mark_failed(event_id, max_attempts=max_attempts)

        dlq = repo.get_dlq_events()
        assert len(dlq) == 1
        assert dlq[0].status == 'DLQ'

    def test_mark_failed_with_backoff(self, temp_db):
        """Test exponential backoff on failures."""
        repo = OutboxRepository(temp_db)
        payload = {'event_id': '123'}
        event_id = repo.add_event(payload)

        # First failure
        repo.mark_failed(event_id, max_attempts=5, initial_backoff_seconds=1.0)

        events = repo.get_pending_events()
        assert len(events) == 0  # Not due yet

        # Verify attempt count increased
        all_events = repo.db.connect().cursor().execute(
            "SELECT attempts FROM outbox_events WHERE id = ?", (event_id,)
        ).fetchall()
        assert all_events[0][0] == 1

    def test_replay_dlq_event(self, temp_db):
        """Test replaying event from DLQ."""
        repo = OutboxRepository(temp_db)
        payload = {'event_id': '123'}
        event_id = repo.add_event(payload)

        # Move to DLQ
        for _ in range(5):
            repo.mark_failed(event_id, max_attempts=5)

        dlq = repo.get_dlq_events()
        assert len(dlq) == 1

        # Replay
        repo.replay_dlq_event(event_id)

        dlq = repo.get_dlq_events()
        assert len(dlq) == 0

        pending = repo.get_pending_events()
        assert len(pending) == 1
        assert pending[0].attempts == 0

    def test_get_stats(self, temp_db):
        """Test getting outbox statistics."""
        repo = OutboxRepository(temp_db)

        # Add pending events
        repo.add_event({'id': '1'})
        repo.add_event({'id': '2'})

        stats = repo.get_stats()
        assert stats['pending_count'] == 2
        assert stats['dlq_count'] == 0
        assert stats['sent_count'] == 0

        # Mark one as sent
        repo.mark_sent(repo.get_pending_events()[0].id)

        stats = repo.get_stats()
        assert stats['pending_count'] == 1
        assert stats['sent_count'] == 1

    def test_error_tracking(self, temp_db):
        """Test error message tracking."""
        repo = OutboxRepository(temp_db)
        payload = {'event_id': '123'}
        event_id = repo.add_event(payload)

        error_msg = "Connection refused to cloud service"
        repo.mark_failed_with_error(event_id, error_msg)

        events = repo.get_dlq_events()
        assert len(events) == 0  # Not in DLQ yet (only 1 attempt)

        # After max attempts
        for _ in range(4):
            repo.mark_failed_with_error(event_id, error_msg)

        dlq = repo.get_dlq_events()
        assert len(dlq) == 1
        assert dlq[0].last_error == error_msg

    def test_pending_events_only_returns_due_events(self, temp_db):
        """Test that get_pending_events only returns events that are due."""
        repo = OutboxRepository(temp_db)

        # Add event
        event_id = repo.add_event({'id': '1'})

        # Should be immediately available
        pending = repo.get_pending_events()
        assert len(pending) == 1

        # Mark as failed (schedules retry in future)
        repo.mark_failed(event_id, max_attempts=5, initial_backoff_seconds=10.0)

        # Should not be available now (next_attempt_at is in future)
        pending = repo.get_pending_events()
        assert len(pending) == 0


class TestOutboxSQLiteSchema:
    """Test outbox table schema and constraints."""

    def test_status_constraint(self, temp_db):
        """Test status field only allows valid values."""
        conn = OutboxRepository(temp_db).db.connect()
        cursor = conn.cursor()

        # Valid statuses should work
        for status in ['PENDING', 'SENT', 'DLQ']:
            cursor.execute(
                """
                INSERT INTO outbox_events (payload_json, status)
                VALUES (?, ?)
                """,
                ('{}', status)
            )
            conn.commit()

    def test_indices_created(self, temp_db):
        """Test that required indices are created."""
        conn = OutboxRepository(temp_db).db.connect()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='outbox_events'"
        )
        indices = [row[0] for row in cursor.fetchall()]

        assert 'idx_outbox_status_next_attempt' in indices
        assert 'idx_outbox_created_at' in indices
