"""
Embedding encryption at rest using AES-GCM with HKDF key derivation.

Master key storage priority:
  1. macOS Keychain (via keyring library) when available
  2. SENTINELID_MASTER_KEY environment variable (dev/CI fallback)

Per-template keys are derived via HKDF(master_key, template_id + salt) so that
compromising one template key does not reveal the master key or any sibling key.

Format of an encrypted blob:
  [4 bytes: magic 0x53454E43 "SENC"] [1 byte: version=1]
  [16 bytes: salt] [12 bytes: nonce] [N bytes: GCM ciphertext+tag]
"""
import os
import secrets
import struct
import logging
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

_BLOB_MAGIC = b"SENC"
_BLOB_VERSION = 1
_KEY_BYTES = 32  # AES-256
_SALT_BYTES = 16
_NONCE_BYTES = 12
_KEYCHAIN_SERVICE = "com.sentinelid.edge"
_KEYCHAIN_ACCOUNT = "master_encryption_key"
_FALLBACK_OVERRIDE_ENV = "ALLOW_KEYCHAIN_FALLBACK"


def _keychain_fallback_allowed() -> bool:
    return os.environ.get(_FALLBACK_OVERRIDE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _prod_keychain_guard(context: str) -> None:
    if os.environ.get("EDGE_ENV", "dev").strip().lower() != "prod":
        return
    if _keychain_fallback_allowed():
        logger.warning(
            "%s is using non-keychain storage in EDGE_ENV=prod because %s is enabled",
            context,
            _FALLBACK_OVERRIDE_ENV,
        )
        return
    raise RuntimeError(
        f"{context} requires OS keychain access when EDGE_ENV=prod. "
        f"Restore keychain access or set {_FALLBACK_OVERRIDE_ENV}=1 for controlled debugging."
    )


# ---------------------------------------------------------------------------
# Master key provider
# ---------------------------------------------------------------------------

class MasterKeyProvider:
    """
    Loads or generates the AES-256 master key.

    macOS Keychain is used when available.  The env-var fallback is
    accepted for developer machines and CI where no keychain is present.
    The env var value must be 64 hex characters (32 bytes).
    """

    def __init__(self, keychain_dir: str = ".sentinelid/keys"):
        self._keychain_dir = keychain_dir
        self._cached_key: Optional[bytes] = None

    def get_master_key(self) -> bytes:
        if self._cached_key is not None:
            return self._cached_key

        keychain_available = self._os_keychain_available()
        key = self._load_from_keychain()
        if key is None:
            if not keychain_available:
                _prod_keychain_guard("Master key initialization")
            key = self._load_from_env()
        if key is None:
            key = self._load_from_file()
        if key is None:
            key = self._generate_and_store()

        self._cached_key = key
        return key

    def rotate_master_key(self) -> bytes:
        """Generate and persist a new master key, invalidate cache."""
        new_key = secrets.token_bytes(_KEY_BYTES)
        self._store_key(new_key)
        self._cached_key = new_key
        logger.info("Master encryption key rotated")
        return new_key

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_from_keychain(self) -> Optional[bytes]:
        try:
            import keyring
            raw = keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT)
            if raw:
                key = bytes.fromhex(raw)
                if len(key) != _KEY_BYTES:
                    logger.warning("Keychain entry has wrong length; ignoring")
                    return None
                logger.debug("Master key loaded from OS keychain")
                return key
        except Exception as exc:
            logger.debug("OS keychain unavailable (%s); trying env var", exc)
        return None

    def _os_keychain_available(self) -> bool:
        try:
            import keyring

            keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT)
            return True
        except Exception as exc:
            logger.debug("OS keychain probe failed (%s)", exc)
            return False

    def _load_from_env(self) -> Optional[bytes]:
        raw = os.environ.get("SENTINELID_MASTER_KEY", "")
        if not raw:
            return None
        try:
            key = bytes.fromhex(raw)
            if len(key) != _KEY_BYTES:
                raise ValueError("SENTINELID_MASTER_KEY must be 64 hex chars (32 bytes)")
            logger.debug("Master key loaded from SENTINELID_MASTER_KEY env var")
            return key
        except ValueError as exc:
            raise RuntimeError(f"Invalid SENTINELID_MASTER_KEY: {exc}") from exc

    def _generate_and_store(self) -> bytes:
        key = secrets.token_bytes(_KEY_BYTES)
        self._store_key(key)
        logger.info("Generated new master encryption key")
        return key

    def _store_key(self, key: bytes):
        hex_key = key.hex()
        stored = False

        # Try keychain first
        try:
            import keyring
            keyring.set_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT, hex_key)
            logger.info("Master key stored in OS keychain")
            stored = True
        except Exception as exc:
            logger.warning("Could not store key in OS keychain (%s)", exc)

        # Fallback: write to a restricted file in the key directory
        if not stored:
            _prod_keychain_guard("Master key storage")
            import pathlib
            key_dir = pathlib.Path(self._keychain_dir)
            key_dir.mkdir(parents=True, exist_ok=True)
            key_file = key_dir / "master_key.hex"
            key_file.write_text(hex_key)
            key_file.chmod(0o600)
            logger.info("Master key stored in %s (keychain unavailable)", key_file)

    def _load_from_file(self) -> Optional[bytes]:
        """Read key from fallback file (used if keychain unavailable at load time)."""
        import pathlib
        key_file = pathlib.Path(self._keychain_dir) / "master_key.hex"
        if not key_file.exists():
            return None
        try:
            raw = key_file.read_text().strip()
            key = bytes.fromhex(raw)
            if len(key) != _KEY_BYTES:
                return None
            logger.debug("Master key loaded from fallback file")
            return key
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Per-template key derivation
# ---------------------------------------------------------------------------

def derive_template_key(master_key: bytes, template_id: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit AES key for a specific template using HKDF-SHA256.

    Info string binds the derived key to the template_id so that two
    templates with the same salt yield different keys.

    Args:
        master_key: 32-byte master AES key
        template_id: Unique identifier for the template
        salt: 16-byte random salt (stored alongside the blob)

    Returns:
        32-byte derived key
    """
    info = f"sentinelid-template-v1:{template_id}".encode()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_BYTES,
        salt=salt,
        info=info,
        backend=default_backend(),
    )
    return hkdf.derive(master_key)


# ---------------------------------------------------------------------------
# Encrypt / decrypt embedding blobs
# ---------------------------------------------------------------------------

def encrypt_embedding(master_key: bytes, template_id: str, embedding: bytes) -> bytes:
    """
    Encrypt a raw embedding with AES-256-GCM.

    Returns a self-describing blob that includes salt and nonce.

    Args:
        master_key: 32-byte master key
        template_id: Template identifier (used in key derivation)
        embedding: Raw serialised embedding bytes

    Returns:
        Encrypted blob (magic + version + salt + nonce + ciphertext)
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    nonce = secrets.token_bytes(_NONCE_BYTES)
    derived_key = derive_template_key(master_key, template_id, salt)
    aesgcm = AESGCM(derived_key)
    # Additional data binds ciphertext to the template_id at verify time
    aad = f"template:{template_id}".encode()
    ciphertext = aesgcm.encrypt(nonce, embedding, aad)

    header = _BLOB_MAGIC + struct.pack("B", _BLOB_VERSION)
    return header + salt + nonce + ciphertext


def decrypt_embedding(master_key: bytes, template_id: str, blob: bytes) -> bytes:
    """
    Decrypt an encrypted embedding blob.

    Args:
        master_key: 32-byte master key
        template_id: Template identifier (must match the one used at encryption)
        blob: Encrypted blob returned by encrypt_embedding

    Returns:
        Raw embedding bytes

    Raises:
        ValueError: If the blob is malformed or the tag is invalid
    """
    header_len = len(_BLOB_MAGIC) + 1  # magic + version byte
    min_len = header_len + _SALT_BYTES + _NONCE_BYTES
    if len(blob) < min_len:
        raise ValueError("Encrypted blob is too short")

    magic = blob[:4]
    if magic != _BLOB_MAGIC:
        raise ValueError(f"Invalid blob magic: {magic!r}")

    version = blob[4]
    if version != _BLOB_VERSION:
        raise ValueError(f"Unsupported blob version: {version}")

    offset = header_len
    salt = blob[offset: offset + _SALT_BYTES]
    offset += _SALT_BYTES
    nonce = blob[offset: offset + _NONCE_BYTES]
    offset += _NONCE_BYTES
    ciphertext = blob[offset:]

    derived_key = derive_template_key(master_key, template_id, salt)
    aesgcm = AESGCM(derived_key)
    aad = f"template:{template_id}".encode()
    try:
        return aesgcm.decrypt(nonce, ciphertext, aad)
    except Exception as exc:
        raise ValueError("Decryption failed: authentication tag mismatch") from exc


def rewrap_blob(old_master_key: bytes, new_master_key: bytes, template_id: str, blob: bytes) -> bytes:
    """
    Decrypt with old key and re-encrypt with new key (used during rotation).

    Args:
        old_master_key: Current master key
        new_master_key: New master key
        template_id: Template identifier
        blob: Currently encrypted blob

    Returns:
        New encrypted blob using the new master key
    """
    plaintext = decrypt_embedding(old_master_key, template_id, blob)
    return encrypt_embedding(new_master_key, template_id, plaintext)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_provider: Optional[MasterKeyProvider] = None


def get_master_key_provider(keychain_dir: str = ".sentinelid/keys") -> MasterKeyProvider:
    """Return the module-level MasterKeyProvider singleton."""
    global _provider
    if _provider is None:
        _provider = MasterKeyProvider(keychain_dir)
    return _provider
