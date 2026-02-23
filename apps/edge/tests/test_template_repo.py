"""
Tests for TemplateRepository: encrypted storage, list, delete, key rotation.
"""
import secrets
import tempfile
from pathlib import Path

import numpy as np
import pytest

from sentinelid_edge.services.security.encryption import (
    _KEY_BYTES,
    decrypt_embedding,
    get_master_key_provider,
)
from sentinelid_edge.services.storage.db import Database
from sentinelid_edge.services.storage.repo_templates import TemplateRepository, _embedding_to_bytes


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset module-level singletons between tests."""
    import sentinelid_edge.services.security.encryption as enc
    import sentinelid_edge.services.storage.db as db_mod
    old_enc = enc._provider
    old_db = db_mod._db_instance
    enc._provider = None
    db_mod._db_instance = None
    yield
    enc._provider = old_enc
    db_mod._db_instance = old_db


@pytest.fixture
def tmp_env(tmp_path):
    """Provide a temporary DB and keys directory."""
    db_path = str(tmp_path / "test.db")
    key_dir = str(tmp_path / "keys")
    # Set a deterministic master key via env
    import os
    test_key = secrets.token_bytes(_KEY_BYTES)
    os.environ["SENTINELID_MASTER_KEY"] = test_key.hex()
    yield db_path, key_dir, test_key
    # Cleanup
    del os.environ["SENTINELID_MASTER_KEY"]


@pytest.fixture
def repo(tmp_env):
    db_path, key_dir, _ = tmp_env
    return TemplateRepository(db_path=db_path, keychain_dir=key_dir)


def _rand_embedding(dim: int = 128):
    return np.random.rand(dim).astype(np.float32)


class TestTemplateRepository:
    def test_store_and_load(self, repo):
        embedding = _rand_embedding()
        tid = repo.store_template("user1", embedding)
        assert tid

        template = repo.load_template(tid)
        assert template is not None
        np.testing.assert_array_almost_equal(template.embedding, embedding)

    def test_stored_blob_is_not_plaintext(self, tmp_env):
        db_path, key_dir, master_key = tmp_env
        repo = TemplateRepository(db_path=db_path, keychain_dir=key_dir)
        embedding = _rand_embedding()
        raw_bytes = _embedding_to_bytes(embedding)
        tid = repo.store_template("user1", embedding)

        # Read raw blob from DB
        import sqlite3
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT encrypted_blob FROM templates WHERE template_id = ?", (tid,)).fetchone()
        conn.close()
        blob = bytes(row[0])

        # Raw float bytes must not appear in the blob
        assert raw_bytes not in blob

    def test_blob_has_senc_magic(self, tmp_env):
        db_path, key_dir, _ = tmp_env
        repo = TemplateRepository(db_path=db_path, keychain_dir=key_dir)
        tid = repo.store_template("user1", _rand_embedding())

        import sqlite3
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT encrypted_blob FROM templates WHERE template_id = ?", (tid,)).fetchone()
        conn.close()
        assert bytes(row[0])[:4] == b"SENC"

    def test_list_templates(self, repo):
        repo.store_template("alice", _rand_embedding())
        repo.store_template("bob", _rand_embedding())
        templates = repo.list_templates()
        assert len(templates) == 2
        labels = {t.label for t in templates}
        assert labels == {"alice", "bob"}
        # No embedding in listed results
        for t in templates:
            assert t.embedding is None

    def test_delete_template(self, repo):
        tid = repo.store_template("user1", _rand_embedding())
        deleted = repo.delete_template(tid)
        assert deleted is True
        assert repo.load_template(tid) is None

    def test_delete_nonexistent_returns_false(self, repo):
        assert repo.delete_template("nonexistent-id") is False

    def test_delete_all(self, repo):
        repo.store_template("u1", _rand_embedding())
        repo.store_template("u2", _rand_embedding())
        count = repo.delete_all_templates()
        assert count == 2
        assert repo.count_templates() == 0

    def test_count(self, repo):
        assert repo.count_templates() == 0
        repo.store_template("u1", _rand_embedding())
        assert repo.count_templates() == 1

    def test_rewrap_all_blobs(self, tmp_env):
        """Key rotation rewraps all blobs; new key decrypts correctly."""
        db_path, key_dir, old_master_key = tmp_env
        repo = TemplateRepository(db_path=db_path, keychain_dir=key_dir)

        embeddings = {}
        for label in ("alice", "bob", "carol"):
            emb = _rand_embedding()
            embeddings[repo.store_template(label, emb)] = emb

        new_master_key = secrets.token_bytes(_KEY_BYTES)
        rewrapped = repo.rewrap_all_blobs(new_master_key)
        assert rewrapped == 3

        # Update cache to new key
        import sentinelid_edge.services.security.encryption as enc
        enc._provider._cached_key = new_master_key
        import os
        os.environ["SENTINELID_MASTER_KEY"] = new_master_key.hex()

        # All templates readable with new key
        for tid, original_emb in embeddings.items():
            template = repo.load_template(tid)
            np.testing.assert_array_almost_equal(template.embedding, original_emb)

    def test_rewrap_atomicity_on_failure(self, tmp_env, monkeypatch):
        """If rewrap fails mid-way, the DB is unchanged (rollback)."""
        db_path, key_dir, master_key = tmp_env
        repo = TemplateRepository(db_path=db_path, keychain_dir=key_dir)

        emb = _rand_embedding()
        tid = repo.store_template("user1", emb)

        # Simulate a failure during rewrap by patching where it is used
        import sentinelid_edge.services.storage.repo_templates as repo_mod
        original_rewrap = repo_mod.rewrap_blob

        call_count = [0]

        def fail_on_second(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 1:
                raise RuntimeError("Simulated failure")
            return original_rewrap(*args, **kwargs)

        monkeypatch.setattr(repo_mod, "rewrap_blob", fail_on_second)

        new_key = secrets.token_bytes(_KEY_BYTES)
        with pytest.raises(RuntimeError):
            repo.rewrap_all_blobs(new_key)

        # Old key still works
        template = repo.load_template(tid)
        np.testing.assert_array_almost_equal(template.embedding, emb)
