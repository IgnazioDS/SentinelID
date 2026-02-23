"""
Template repository: stores and retrieves encrypted face embeddings.

Templates are stored as AES-GCM encrypted blobs in SQLite so the database
never contains plaintext float vectors.  Each template has its own derived
key (HKDF from master key + per-template salt) so compromising one does
not reveal others.
"""
import json
import struct
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .db import get_database
from ..security.encryption import (
    encrypt_embedding,
    decrypt_embedding,
    rewrap_blob,
    get_master_key_provider,
)


def _embedding_to_bytes(embedding) -> bytes:
    """Serialise a numpy float32 vector to raw bytes."""
    arr = np.asarray(embedding, dtype=np.float32)
    return arr.tobytes()


def _bytes_to_embedding(raw: bytes):
    """Deserialise raw bytes back to a numpy float32 vector."""
    return np.frombuffer(raw, dtype=np.float32)


@dataclass
class Template:
    """In-memory representation of a stored template."""

    template_id: str
    label: str
    created_at: int
    # embedding is only populated when loaded with decrypt=True
    embedding: Optional[object] = None


class TemplateRepository:
    """
    CRUD operations for face embedding templates.

    All embeddings are encrypted before being written to the database.
    The plaintext embedding is never persisted.
    """

    def __init__(
        self,
        db_path: str = ".sentinelid/audit.db",
        keychain_dir: str = ".sentinelid/keys",
    ):
        self.db = get_database(db_path)
        self._key_provider = get_master_key_provider(keychain_dir)
        self._ensure_schema()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def store_template(self, label: str, embedding) -> str:
        """
        Encrypt and store a face embedding.

        Args:
            label: Human-readable label (e.g. username or "default")
            embedding: numpy array or list of floats

        Returns:
            template_id (UUID string)
        """
        template_id = str(uuid.uuid4())
        raw_bytes = _embedding_to_bytes(embedding)
        master_key = self._key_provider.get_master_key()
        encrypted_blob = encrypt_embedding(master_key, template_id, raw_bytes)
        created_at = int(time.time())

        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO templates (template_id, label, encrypted_blob, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (template_id, label, encrypted_blob, created_at),
        )
        conn.commit()
        return template_id

    def load_template(self, template_id: str) -> Optional[Template]:
        """
        Load and decrypt a template by ID.

        Returns:
            Template with embedding populated, or None if not found
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT template_id, label, encrypted_blob, created_at FROM templates WHERE template_id = ?",
            (template_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        master_key = self._key_provider.get_master_key()
        raw_bytes = decrypt_embedding(master_key, row["template_id"], bytes(row["encrypted_blob"]))
        embedding = _bytes_to_embedding(raw_bytes)

        return Template(
            template_id=row["template_id"],
            label=row["label"],
            created_at=row["created_at"],
            embedding=embedding,
        )

    def load_latest_template(self) -> Optional[Template]:
        """
        Load the newest template by created_at and decrypt it.
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT template_id, label, encrypted_blob, created_at
            FROM templates
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row is None:
            return None
        master_key = self._key_provider.get_master_key()
        raw_bytes = decrypt_embedding(master_key, row["template_id"], bytes(row["encrypted_blob"]))
        embedding = _bytes_to_embedding(raw_bytes)
        return Template(
            template_id=row["template_id"],
            label=row["label"],
            created_at=row["created_at"],
            embedding=embedding,
        )

    def list_templates(self) -> List[Template]:
        """
        List all templates (metadata only, no decryption).

        Returns:
            List of Template objects without embedding field populated
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT template_id, label, created_at FROM templates ORDER BY created_at ASC"
        )
        rows = cursor.fetchall()
        return [
            Template(
                template_id=row["template_id"],
                label=row["label"],
                created_at=row["created_at"],
                embedding=None,
            )
            for row in rows
        ]

    def delete_template(self, template_id: str) -> bool:
        """
        Delete a single template.

        Returns:
            True if a row was deleted, False if not found
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM templates WHERE template_id = ?", (template_id,))
        conn.commit()
        return cursor.rowcount > 0

    def delete_all_templates(self) -> int:
        """
        Delete all templates.

        Returns:
            Number of templates deleted
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM templates")
        count = cursor.fetchone()[0]
        cursor.execute("DELETE FROM templates")
        conn.commit()
        return count

    def count_templates(self) -> int:
        """Return total number of stored templates."""
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM templates")
        return cursor.fetchone()[0]

    # ------------------------------------------------------------------
    # Key rotation support
    # ------------------------------------------------------------------

    def rewrap_all_blobs(self, new_master_key: bytes) -> int:
        """
        Re-encrypt all template blobs with a new master key.

        This is called during key rotation.  The operation is performed
        inside a single SQLite transaction so it is atomic: either all
        blobs are rewrapped or none are (on failure the DB is unchanged).

        Args:
            new_master_key: The new 32-byte master key

        Returns:
            Number of templates rewrapped

        Raises:
            Exception: If any blob fails to rewrap (rolls back all changes)
        """
        old_master_key = self._key_provider.get_master_key()
        conn = self.db.connect()
        cursor = conn.cursor()

        cursor.execute("SELECT template_id, encrypted_blob FROM templates")
        rows = cursor.fetchall()

        updates = []
        for row in rows:
            new_blob = rewrap_blob(
                old_master_key,
                new_master_key,
                row["template_id"],
                bytes(row["encrypted_blob"]),
            )
            updates.append((new_blob, row["template_id"]))

        # Apply all updates in a single transaction
        cursor.execute("BEGIN EXCLUSIVE")
        try:
            for new_blob, template_id in updates:
                cursor.execute(
                    "UPDATE templates SET encrypted_blob = ? WHERE template_id = ?",
                    (new_blob, template_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return len(updates)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self):
        """Create the templates table if it does not exist."""
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL,
                encrypted_blob BLOB NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_templates_label ON templates(label)"
        )
        conn.commit()
