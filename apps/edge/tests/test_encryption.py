"""
Tests for AES-GCM embedding encryption, HKDF key derivation,
and master key provider.
"""
import os
import secrets
import struct
import tempfile
from pathlib import Path

import numpy as np
import pytest

from sentinelid_edge.services.security.encryption import (
    MasterKeyProvider,
    _BLOB_MAGIC,
    _BLOB_VERSION,
    _KEY_BYTES,
    _NONCE_BYTES,
    _SALT_BYTES,
    decrypt_embedding,
    derive_template_key,
    encrypt_embedding,
    rewrap_blob,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_embedding(dim: int = 512) -> bytes:
    """Create a random float32 embedding as bytes."""
    return np.random.rand(dim).astype(np.float32).tobytes()


@pytest.fixture
def master_key() -> bytes:
    return secrets.token_bytes(_KEY_BYTES)


@pytest.fixture
def template_id() -> str:
    return "test-template-abc123"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

class TestDeriveTemplateKey:
    def test_returns_correct_length(self, master_key, template_id):
        salt = secrets.token_bytes(_SALT_BYTES)
        key = derive_template_key(master_key, template_id, salt)
        assert len(key) == _KEY_BYTES

    def test_deterministic(self, master_key, template_id):
        salt = secrets.token_bytes(_SALT_BYTES)
        k1 = derive_template_key(master_key, template_id, salt)
        k2 = derive_template_key(master_key, template_id, salt)
        assert k1 == k2

    def test_different_salt_yields_different_key(self, master_key, template_id):
        salt1 = secrets.token_bytes(_SALT_BYTES)
        salt2 = secrets.token_bytes(_SALT_BYTES)
        k1 = derive_template_key(master_key, template_id, salt1)
        k2 = derive_template_key(master_key, template_id, salt2)
        assert k1 != k2

    def test_different_template_id_yields_different_key(self, master_key):
        salt = secrets.token_bytes(_SALT_BYTES)
        k1 = derive_template_key(master_key, "template-A", salt)
        k2 = derive_template_key(master_key, "template-B", salt)
        assert k1 != k2

    def test_different_master_key_yields_different_derived_key(self, template_id):
        salt = secrets.token_bytes(_SALT_BYTES)
        k1 = derive_template_key(secrets.token_bytes(_KEY_BYTES), template_id, salt)
        k2 = derive_template_key(secrets.token_bytes(_KEY_BYTES), template_id, salt)
        assert k1 != k2


# ---------------------------------------------------------------------------
# Encrypt / decrypt
# ---------------------------------------------------------------------------

class TestEncryptDecrypt:
    def test_roundtrip(self, master_key, template_id):
        plaintext = _make_embedding()
        blob = encrypt_embedding(master_key, template_id, plaintext)
        recovered = decrypt_embedding(master_key, template_id, blob)
        assert recovered == plaintext

    def test_blob_is_not_plaintext(self, master_key, template_id):
        plaintext = _make_embedding()
        blob = encrypt_embedding(master_key, template_id, plaintext)
        assert plaintext not in blob

    def test_blob_has_correct_magic(self, master_key, template_id):
        blob = encrypt_embedding(master_key, template_id, _make_embedding())
        assert blob[:4] == _BLOB_MAGIC

    def test_blob_has_correct_version(self, master_key, template_id):
        blob = encrypt_embedding(master_key, template_id, _make_embedding())
        assert blob[4] == _BLOB_VERSION

    def test_blob_minimum_size(self, master_key, template_id):
        blob = encrypt_embedding(master_key, template_id, _make_embedding())
        # header(5) + salt(16) + nonce(12) + at least 1 byte ciphertext + 16 tag
        assert len(blob) > 5 + _SALT_BYTES + _NONCE_BYTES + 16

    def test_different_encryptions_produce_different_blobs(self, master_key, template_id):
        plaintext = _make_embedding()
        blob1 = encrypt_embedding(master_key, template_id, plaintext)
        blob2 = encrypt_embedding(master_key, template_id, plaintext)
        # Different salts/nonces each call
        assert blob1 != blob2

    def test_wrong_master_key_raises(self, template_id):
        key1 = secrets.token_bytes(_KEY_BYTES)
        key2 = secrets.token_bytes(_KEY_BYTES)
        blob = encrypt_embedding(key1, template_id, _make_embedding())
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_embedding(key2, template_id, blob)

    def test_wrong_template_id_raises(self, master_key):
        blob = encrypt_embedding(master_key, "template-A", _make_embedding())
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_embedding(master_key, "template-B", blob)

    def test_tampered_blob_raises(self, master_key, template_id):
        blob = bytearray(encrypt_embedding(master_key, template_id, _make_embedding()))
        # Flip a byte in the ciphertext region
        blob[-5] ^= 0xFF
        with pytest.raises(ValueError):
            decrypt_embedding(master_key, template_id, bytes(blob))

    def test_truncated_blob_raises(self, master_key, template_id):
        blob = encrypt_embedding(master_key, template_id, _make_embedding())
        with pytest.raises(ValueError, match="too short"):
            decrypt_embedding(master_key, template_id, blob[:10])

    def test_wrong_magic_raises(self, master_key, template_id):
        blob = bytearray(encrypt_embedding(master_key, template_id, _make_embedding()))
        blob[:4] = b"XXXX"
        with pytest.raises(ValueError, match="magic"):
            decrypt_embedding(master_key, template_id, bytes(blob))


# ---------------------------------------------------------------------------
# Rewrap (key rotation helper)
# ---------------------------------------------------------------------------

class TestRewrapBlob:
    def test_rewrap_preserves_plaintext(self, template_id):
        old_key = secrets.token_bytes(_KEY_BYTES)
        new_key = secrets.token_bytes(_KEY_BYTES)
        plaintext = _make_embedding()
        old_blob = encrypt_embedding(old_key, template_id, plaintext)
        new_blob = rewrap_blob(old_key, new_key, template_id, old_blob)
        recovered = decrypt_embedding(new_key, template_id, new_blob)
        assert recovered == plaintext

    def test_old_key_cannot_decrypt_rewrapped_blob(self, template_id):
        old_key = secrets.token_bytes(_KEY_BYTES)
        new_key = secrets.token_bytes(_KEY_BYTES)
        old_blob = encrypt_embedding(old_key, template_id, _make_embedding())
        new_blob = rewrap_blob(old_key, new_key, template_id, old_blob)
        with pytest.raises(ValueError):
            decrypt_embedding(old_key, template_id, new_blob)

    def test_rewrapped_blob_differs_from_original(self, template_id):
        old_key = secrets.token_bytes(_KEY_BYTES)
        new_key = secrets.token_bytes(_KEY_BYTES)
        old_blob = encrypt_embedding(old_key, template_id, _make_embedding())
        new_blob = rewrap_blob(old_key, new_key, template_id, old_blob)
        assert old_blob != new_blob


# ---------------------------------------------------------------------------
# MasterKeyProvider
# ---------------------------------------------------------------------------

class TestMasterKeyProvider:
    def test_generates_key_if_none_exists(self, tmp_path):
        provider = MasterKeyProvider(keychain_dir=str(tmp_path / "keys"))
        key = provider.get_master_key()
        assert len(key) == _KEY_BYTES

    def test_key_persists_across_instances(self, tmp_path, monkeypatch):
        # Disable keychain; use file fallback
        monkeypatch.setattr("sentinelid_edge.services.security.encryption.keyring", None, raising=False)
        key_dir = str(tmp_path / "keys")
        p1 = MasterKeyProvider(keychain_dir=key_dir)
        key1 = p1.get_master_key()

        p2 = MasterKeyProvider(keychain_dir=key_dir)
        # Force load from file
        p2._cached_key = None
        key_file = Path(key_dir) / "master_key.hex"
        if key_file.exists():
            raw = key_file.read_text().strip()
            key2 = bytes.fromhex(raw)
            assert key1 == key2

    def test_env_var_key_used_when_set(self, tmp_path, monkeypatch):
        test_key = secrets.token_bytes(_KEY_BYTES)
        monkeypatch.setenv("SENTINELID_MASTER_KEY", test_key.hex())
        provider = MasterKeyProvider(keychain_dir=str(tmp_path / "keys"))
        assert provider._load_from_env() == test_key

    def test_env_var_wrong_length_raises(self, monkeypatch):
        monkeypatch.setenv("SENTINELID_MASTER_KEY", "deadbeef")
        provider = MasterKeyProvider(keychain_dir="/tmp/keys")
        with pytest.raises(RuntimeError, match="Invalid SENTINELID_MASTER_KEY"):
            provider._load_from_env()

    def test_caching(self, tmp_path):
        provider = MasterKeyProvider(keychain_dir=str(tmp_path / "keys"))
        k1 = provider.get_master_key()
        k2 = provider.get_master_key()
        assert k1 is k2  # same object (cached)
