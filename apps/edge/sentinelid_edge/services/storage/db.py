"""
SQLite database initialization and connection management.
"""
import sqlite3
from pathlib import Path
from typing import Optional


class Database:
    """SQLite database connection and schema management."""

    def __init__(self, db_path: str = ".sentinelid/audit.db"):
        """
        Initialize database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """
        Get or create database connection.

        Returns:
            SQLite connection
        """
        if self.connection is None:
            self.connection = sqlite3.connect(str(self.db_path))
            self.connection.row_factory = sqlite3.Row
        return self.connection

    def init_schema(self):
        """Initialize database schema (audit log and outbox tables)."""
        conn = self.connect()
        cursor = conn.cursor()

        # Audit events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                timestamp INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason_codes TEXT,
                similarity_score REAL,
                risk_score REAL,
                liveness_passed INTEGER,
                session_id TEXT,
                prev_hash TEXT,
                hash TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Telemetry outbox table for reliable event delivery
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS outbox_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                payload_json TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                next_attempt_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'SENT', 'DLQ')),
                last_error TEXT,
                last_error_at DATETIME
            )
        """)

        # Create indices for efficient queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_outbox_status_next_attempt
            ON outbox_events(status, next_attempt_at)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_outbox_created_at
            ON outbox_events(created_at)
        """)

        conn.commit()

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Global database instance
_db_instance: Optional[Database] = None


def get_database(db_path: str = ".sentinelid/audit.db") -> Database:
    """
    Get global database instance.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Database instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
        _db_instance.init_schema()
    return _db_instance
