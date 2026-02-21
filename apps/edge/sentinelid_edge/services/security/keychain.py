"""
Keychain management for device keypairs.
"""
import os
import json
from typing import Optional, Tuple
from pathlib import Path
from .crypto import CryptoProvider


class Keychain:
    """Manages device cryptographic keys (ED25519)."""

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
        if self.keys_file.exists():
            with open(self.keys_file, 'r') as f:
                keys = json.load(f)
            return keys['private_key'], keys['public_key']

        # Generate new keypair
        private_key, public_key = CryptoProvider.generate_keypair()

        # Store it
        keys_data = {
            'private_key': private_key,
            'public_key': public_key
        }
        with open(self.keys_file, 'w') as f:
            json.dump(keys_data, f)

        # Restrict permissions
        os.chmod(self.keys_file, 0o600)

        return private_key, public_key

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
