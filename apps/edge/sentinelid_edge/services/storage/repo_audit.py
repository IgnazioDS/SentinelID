"""
Audit log repository with hash-chain integrity and encrypted payload storage.
"""

import json
import secrets
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .db import get_database
from ..security.crypto import CryptoProvider
from ..security.encryption import get_master_key_provider

_AUDIT_BLOB_MAGIC = b"SAUD"
_AUDIT_BLOB_VERSION = 1
_AUDIT_KEY_BYTES = 32
_AUDIT_SALT_BYTES = 16
_AUDIT_NONCE_BYTES = 12


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
    request_id: Optional[str] = None
    prev_hash: Optional[str] = None
    hash: Optional[str] = None


class AuditRepository:
    """Manages audit log storage with append-only hash-chain integrity."""

    def __init__(
        self,
        db_path: str = ".sentinelid/audit.db",
        keychain_dir: str = ".sentinelid/keys",
    ):
        """
        Initialize audit repository.

        Args:
            db_path: Path to SQLite database
            keychain_dir: Directory for encryption master key fallback
        """
        self.db = get_database(db_path)
        self._key_provider = get_master_key_provider(keychain_dir)

    def write_event(self, event: AuditEvent) -> str:
        """
        Write audit event to log with hash-chain validation.

        Args:
            event: Audit event to write

        Returns:
            Event hash
        """
        if not event.event_id:
            event.event_id = str(uuid.uuid4())

        if not event.timestamp:
            event.timestamp = int(time.time())

        prev_hash = self._get_last_hash()
        if prev_hash is None:
            prev_hash = "0" * 64  # Genesis block
        event.prev_hash = prev_hash

        hash_payload = self._build_hash_payload(
            event_id=event.event_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            outcome=event.outcome,
            reason_codes=event.reason_codes,
            similarity_score=event.similarity_score,
            risk_score=event.risk_score,
            liveness_passed=event.liveness_passed,
            session_id=event.session_id,
            request_id=event.request_id,
        )
        event_data = json.dumps(hash_payload).encode("utf-8")
        event.hash = CryptoProvider.hash_chain(prev_hash, event_data)
        encrypted_payload = self._encrypt_payload(event.event_id, hash_payload)

        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_events (
                event_id, timestamp, event_type, outcome, reason_codes,
                similarity_score, risk_score, liveness_passed, session_id, request_id,
                prev_hash, hash, encrypted_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.timestamp,
                event.event_type,
                event.outcome,
                None,
                None,
                None,
                None,
                None,
                None,
                event.prev_hash,
                event.hash,
                encrypted_payload,
            ),
        )
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
        cursor.execute(
            """
            SELECT event_id, timestamp, event_type, outcome, reason_codes,
                   similarity_score, risk_score, liveness_passed, session_id, request_id,
                   prev_hash, hash, encrypted_payload
            FROM audit_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )

        rows = cursor.fetchall()
        events: List[AuditEvent] = []
        for row in rows:
            payload = self._payload_from_row(row)
            events.append(
                AuditEvent(
                    event_id=payload["event_id"],
                    timestamp=payload["timestamp"],
                    event_type=payload["event_type"],
                    outcome=payload["outcome"],
                    reason_codes=payload["reason_codes"],
                    similarity_score=payload["similarity_score"],
                    risk_score=payload["risk_score"],
                    liveness_passed=payload["liveness_passed"],
                    session_id=payload["session_id"],
                    request_id=payload.get("request_id"),
                    prev_hash=row["prev_hash"],
                    hash=row["hash"],
                )
            )
        return list(reversed(events))  # chronological order

    def verify_chain_integrity(self) -> bool:
        """
        Verify hash-chain integrity of entire audit log.

        Returns:
            True if chain is valid, False otherwise
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT event_id, timestamp, event_type, outcome, reason_codes,
                   similarity_score, risk_score, liveness_passed, session_id, request_id,
                   prev_hash, hash, encrypted_payload
            FROM audit_events
            ORDER BY id ASC
            """
        )

        rows = cursor.fetchall()
        expected_prev_hash = "0" * 64  # Genesis block
        for row in rows:
            if row["prev_hash"] != expected_prev_hash:
                return False
            try:
                payload = self._payload_from_row(row)
            except Exception:
                return False
            event_data = json.dumps(payload).encode("utf-8")
            computed_hash = CryptoProvider.hash_chain(expected_prev_hash, event_data)
            if computed_hash != row["hash"]:
                return False
            expected_prev_hash = row["hash"]
        return True

    def _get_last_hash(self) -> Optional[str]:
        """Get the hash of the last audit event."""
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return row["hash"] if row else None

    @staticmethod
    def _build_hash_payload(
        *,
        event_id: str,
        timestamp: int,
        event_type: str,
        outcome: str,
        reason_codes: Any,
        similarity_score: Optional[Any],
        risk_score: Optional[Any],
        liveness_passed: Optional[Any],
        session_id: Optional[Any],
        request_id: Optional[Any],
    ) -> Dict[str, Any]:
        if not isinstance(reason_codes, list):
            reason_codes = []
        normalized: Dict[str, Any] = {
            "event_id": str(event_id),
            "timestamp": int(timestamp),
            "event_type": str(event_type),
            "outcome": str(outcome),
            "reason_codes": [str(code) for code in reason_codes],
            "similarity_score": float(similarity_score) if similarity_score is not None else None,
            "risk_score": float(risk_score) if risk_score is not None else None,
            "liveness_passed": (
                bool(liveness_passed) if liveness_passed is not None else None
            ),
            "session_id": str(session_id) if session_id is not None else None,
        }
        if request_id is not None:
            normalized["request_id"] = str(request_id)
        return normalized

    def _payload_from_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        encrypted_blob = row["encrypted_payload"]
        if encrypted_blob is not None:
            raw = self._decrypt_payload(row["event_id"], bytes(encrypted_blob))
            if not isinstance(raw, dict):
                raise ValueError("Encrypted audit payload is not an object")

            payload = self._build_hash_payload(
                event_id=raw.get("event_id", row["event_id"]),
                timestamp=raw.get("timestamp", row["timestamp"]),
                event_type=raw.get("event_type", row["event_type"]),
                outcome=raw.get("outcome", row["outcome"]),
                reason_codes=raw.get("reason_codes", []),
                similarity_score=raw.get("similarity_score"),
                risk_score=raw.get("risk_score"),
                liveness_passed=raw.get("liveness_passed"),
                session_id=raw.get("session_id"),
                request_id=raw.get("request_id"),
            )
            if payload["event_id"] != row["event_id"]:
                raise ValueError("Encrypted payload event_id mismatch")
            if payload["event_type"] != row["event_type"]:
                raise ValueError("Encrypted payload event_type mismatch")
            if payload["outcome"] != row["outcome"]:
                raise ValueError("Encrypted payload outcome mismatch")
            return payload

        # Legacy plaintext fallback
        reason_codes: List[str]
        try:
            reason_codes = json.loads(row["reason_codes"] or "[]")
        except Exception:
            reason_codes = []
        return self._build_hash_payload(
            event_id=row["event_id"],
            timestamp=row["timestamp"],
            event_type=row["event_type"],
            outcome=row["outcome"],
            reason_codes=reason_codes,
            similarity_score=row["similarity_score"],
            risk_score=row["risk_score"],
            liveness_passed=row["liveness_passed"],
            session_id=row["session_id"],
            request_id=row["request_id"],
        )

    @staticmethod
    def _derive_audit_key(master_key: bytes, event_id: str, salt: bytes) -> bytes:
        info = f"sentinelid-audit-v1:{event_id}".encode("utf-8")
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=_AUDIT_KEY_BYTES,
            salt=salt,
            info=info,
            backend=default_backend(),
        )
        return hkdf.derive(master_key)

    def _encrypt_payload(self, event_id: str, payload: Dict[str, Any]) -> bytes:
        master_key = self._key_provider.get_master_key()
        salt = secrets.token_bytes(_AUDIT_SALT_BYTES)
        nonce = secrets.token_bytes(_AUDIT_NONCE_BYTES)
        key = self._derive_audit_key(master_key, event_id, salt)
        aesgcm = AESGCM(key)
        aad = f"audit:{event_id}".encode("utf-8")
        plaintext = json.dumps(payload).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
        header = _AUDIT_BLOB_MAGIC + struct.pack("B", _AUDIT_BLOB_VERSION)
        return header + salt + nonce + ciphertext

    def _decrypt_payload(self, event_id: str, blob: bytes) -> Dict[str, Any]:
        header_len = len(_AUDIT_BLOB_MAGIC) + 1
        min_len = header_len + _AUDIT_SALT_BYTES + _AUDIT_NONCE_BYTES
        if len(blob) < min_len:
            raise ValueError("Encrypted audit payload is too short")

        magic = blob[:4]
        if magic != _AUDIT_BLOB_MAGIC:
            raise ValueError("Invalid audit blob magic")
        version = blob[4]
        if version != _AUDIT_BLOB_VERSION:
            raise ValueError("Unsupported audit blob version")

        offset = header_len
        salt = blob[offset: offset + _AUDIT_SALT_BYTES]
        offset += _AUDIT_SALT_BYTES
        nonce = blob[offset: offset + _AUDIT_NONCE_BYTES]
        offset += _AUDIT_NONCE_BYTES
        ciphertext = blob[offset:]

        master_key = self._key_provider.get_master_key()
        key = self._derive_audit_key(master_key, event_id, salt)
        aesgcm = AESGCM(key)
        aad = f"audit:{event_id}".encode("utf-8")
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Decrypted audit payload must be an object")
        return payload
