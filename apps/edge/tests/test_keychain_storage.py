"""Tests for device keypair storage strategy (OS keychain first, file fallback)."""
from __future__ import annotations

import json
import stat
import types

from sentinelid_edge.services.security.keychain import Keychain


def _fake_keyring_module(store: dict[tuple[str, str], str]):
    def get_password(service: str, account: str):
        return store.get((service, account))

    def set_password(service: str, account: str, value: str):
        store[(service, account)] = value

    def delete_password(service: str, account: str):
        store.pop((service, account), None)

    return types.SimpleNamespace(
        get_password=get_password,
        set_password=set_password,
        delete_password=delete_password,
    )


def _failing_keyring_module():
    def fail(*_args, **_kwargs):
        raise RuntimeError("keychain unavailable")

    return types.SimpleNamespace(
        get_password=fail,
        set_password=fail,
        delete_password=fail,
    )


class TestKeychainStorage:
    def test_prefers_os_keychain_when_available(self, tmp_path, monkeypatch):
        store: dict[tuple[str, str], str] = {}
        monkeypatch.setitem(__import__("sys").modules, "keyring", _fake_keyring_module(store))

        key_dir = tmp_path / "keys"
        keychain = Keychain(str(key_dir))

        priv_1, pub_1 = keychain.load_or_generate()
        assert priv_1 and pub_1
        assert not (key_dir / "device_keys.json").exists()

        keychain_again = Keychain(str(key_dir))
        priv_2, pub_2 = keychain_again.load_or_generate()
        assert priv_2 == priv_1
        assert pub_2 == pub_1

        # Ensure payload stored in keyring is valid JSON
        payload = next(iter(store.values()))
        parsed = json.loads(payload)
        assert parsed["private_key"] == priv_1
        assert parsed["public_key"] == pub_1

    def test_falls_back_to_restricted_file_when_keychain_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "keyring", _failing_keyring_module())

        key_dir = tmp_path / "keys"
        key_file = key_dir / "device_keys.json"
        keychain = Keychain(str(key_dir))

        priv_1, pub_1 = keychain.load_or_generate()
        assert priv_1 and pub_1
        assert key_file.exists()

        mode = stat.S_IMODE(key_file.stat().st_mode)
        assert mode == 0o600

        keychain_again = Keychain(str(key_dir))
        priv_2, pub_2 = keychain_again.load_or_generate()
        assert priv_2 == priv_1
        assert pub_2 == pub_1

    def test_clear_keypair_removes_file_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "keyring", _failing_keyring_module())

        key_dir = tmp_path / "keys"
        key_file = key_dir / "device_keys.json"
        keychain = Keychain(str(key_dir))
        keychain.load_or_generate()
        assert key_file.exists()

        keychain.clear_keypair()
        assert not key_file.exists()
