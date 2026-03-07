"""
Keychain management for device keypairs.
"""
import os
import json
import logging
from typing import Tuple, Optional
from pathlib import Path
from .crypto import CryptoProvider

logger = logging.getLogger(__name__)

_KEYCHAIN_SERVICE = "com.sentinelid.edge"
_KEYPAIR_ACCOUNT = "device_keypair_v1"
_FALLBACK_OVERRIDE_ENV = "ALLOW_KEYCHAIN_FALLBACK"


def _keychain_fallback_allowed() -> bool:
    return os.environ.get(_FALLBACK_OVERRIDE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _prod_keychain_guard(context: str) -> None:
    if os.environ.get("EDGE_ENV", "dev").strip().lower() != "prod":
        return
    if _keychain_fallback_allowed():
        logger.warning(
            "%s is using filesystem fallback in EDGE_ENV=prod because %s is enabled",
            context,
            _FALLBACK_OVERRIDE_ENV,
        )
        return
    raise RuntimeError(
        f"{context} requires OS keychain access when EDGE_ENV=prod. "
        f"Restore keychain access or set {_FALLBACK_OVERRIDE_ENV}=1 for controlled debugging."
    )


class Keychain:
    """Manages device cryptographic keys (ED25519) with keychain-first storage."""

    def __init__(self, keychain_dir: str = ".sentinelid/keys"):
        """
        Initialize keychain with storage directory.

        Args:
            keychain_dir: Directory to store keys
        """
        self.keychain_dir = Path(keychain_dir)
        self.keychain_dir.mkdir(parents=True, exist_ok=True)
        self.keys_file = self.keychain_dir / "device_keys.json"

    def load_or_generate(self) -> Tuple[str, str]:
        """
        Load device keypair from storage, or generate if not found.

        Returns:
            Tuple of (private_key_pem, public_key_pem)
        """
        keychain_available = self._os_keychain_available()
        keys = self._load_from_os_keychain()
        if keys is not None:
            return keys

        if not keychain_available:
            _prod_keychain_guard("Device keypair initialization")

        keys = self._load_from_file()
        if keys is not None:
            self._store_to_os_keychain(keys)
            return keys

        keys = CryptoProvider.generate_keypair()
        stored_in_keychain = self._store_to_os_keychain(keys)
        if stored_in_keychain:
            self._delete_file_copy()
        else:
            self._store_to_file(keys)
        return keys

    def rotate_keypair(self) -> Tuple[str, str]:
        """
        Generate and persist a fresh keypair.

        Returns:
            Tuple of (private_key_pem, public_key_pem)
        """
        keys = CryptoProvider.generate_keypair()
        stored_in_keychain = self._store_to_os_keychain(keys)
        if stored_in_keychain:
            self._delete_file_copy()
        else:
            _prod_keychain_guard("Device keypair rotation")
            self._store_to_file(keys)
        return keys

    def clear_keypair(self) -> None:
        """Remove stored keypair from keychain and fallback file."""
        self._delete_from_os_keychain()
        self._delete_file_copy()

    def get_public_key(self) -> str:
        """
        Get the device public key.

        Returns:
            PEM-encoded public key
        """
        _, public_key = self.load_or_generate()
        return public_key

    def get_private_key(self) -> str:
        """
        Get the device private key.

        Returns:
            PEM-encoded private key
        """
        private_key, _ = self.load_or_generate()
        return private_key

    def _load_from_os_keychain(self) -> Optional[Tuple[str, str]]:
        try:
            import keyring

            raw = keyring.get_password(_KEYCHAIN_SERVICE, _KEYPAIR_ACCOUNT)
            if not raw:
                return None
            payload = json.loads(raw)
            private_key = payload.get("private_key")
            public_key = payload.get("public_key")
            if not private_key or not public_key:
                logger.warning("Invalid device keypair payload in keychain entry; ignoring")
                return None
            return private_key, public_key
        except Exception as exc:
            logger.debug("OS keychain unavailable for device keypair (%s)", exc)
            return None

    def _os_keychain_available(self) -> bool:
        try:
            import keyring

            keyring.get_password(_KEYCHAIN_SERVICE, _KEYPAIR_ACCOUNT)
            return True
        except Exception as exc:
            logger.debug("OS keychain probe failed for device keypair (%s)", exc)
            return False

    def _store_to_os_keychain(self, keys: Tuple[str, str]) -> bool:
        private_key, public_key = keys
        payload = json.dumps(
            {
                "private_key": private_key,
                "public_key": public_key,
            }
        )
        try:
            import keyring

            keyring.set_password(_KEYCHAIN_SERVICE, _KEYPAIR_ACCOUNT, payload)
            return True
        except Exception as exc:
            logger.debug("Could not store device keypair in OS keychain (%s)", exc)
            return False

    def _delete_from_os_keychain(self) -> None:
        try:
            import keyring

            keyring.delete_password(_KEYCHAIN_SERVICE, _KEYPAIR_ACCOUNT)
        except Exception:
            pass

    def _load_from_file(self) -> Optional[Tuple[str, str]]:
        if not self.keys_file.exists():
            return None
        try:
            with open(self.keys_file, "r", encoding="utf-8") as f:
                keys = json.load(f)
            private_key = keys.get("private_key")
            public_key = keys.get("public_key")
            if not private_key or not public_key:
                return None
            return private_key, public_key
        except Exception:
            return None

    def _store_to_file(self, keys: Tuple[str, str]) -> None:
        private_key, public_key = keys
        keys_data = {
            "private_key": private_key,
            "public_key": public_key,
        }
        with open(self.keys_file, "w", encoding="utf-8") as f:
            json.dump(keys_data, f)
        os.chmod(self.keys_file, 0o600)

    def _delete_file_copy(self) -> None:
        if self.keys_file.exists():
            self.keys_file.unlink()
