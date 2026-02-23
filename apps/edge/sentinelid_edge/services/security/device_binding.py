"""
Device binding and identification.
"""
import uuid
import json
from pathlib import Path
from .keychain import Keychain
from .crypto import CryptoProvider


class DeviceBinding:
    """Manages device identity and binding."""

    def __init__(self, keychain_dir: str = ".sentinelid/keys"):
        """
        Initialize device binding.

        Args:
            keychain_dir: Directory for key storage
        """
        self.keychain = Keychain(keychain_dir)
        self.keychain_dir = Path(keychain_dir)
        self.device_id_file = self.keychain_dir / "device_id.json"

    def get_device_id(self) -> str:
        """
        Get or create device ID.

        Device ID is derived from the public key hash, ensuring
        consistent identity across restarts.

        Returns:
            Device ID (UUID-like string)
        """
        if self.device_id_file.exists():
            with open(self.device_id_file, 'r') as f:
                data = json.load(f)
            return data['device_id']

        # Generate device ID from public key hash
        public_key = self.keychain.get_public_key()
        key_hash = CryptoProvider.hash_sha256(public_key.encode())
        device_id = str(uuid.UUID(key_hash[:32]))

        # Store it
        device_data = {'device_id': device_id}
        with open(self.device_id_file, 'w') as f:
            json.dump(device_data, f)

        return device_id

    def get_public_key(self) -> str:
        """
        Get the device public key.

        Returns:
            PEM-encoded ED25519 public key
        """
        return self.keychain.get_public_key()

    def sign(self, data: bytes) -> str:
        """
        Sign data with device private key.

        Args:
            data: Bytes to sign

        Returns:
            Hex-encoded signature
        """
        private_key = self.keychain.get_private_key()
        return CryptoProvider.sign(private_key, data)


class DeviceKeychain(DeviceBinding):
    """
    Backward-compatible wrapper used by diagnostics and admin endpoints.
    """

    def get_public_key_fingerprint(self) -> str:
        """Return a stable SHA-256 fingerprint of the device public key."""
        return CryptoProvider.hash_sha256(self.get_public_key().encode())
