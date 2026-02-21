"""
Cryptographic utilities for telemetry signing and device binding.
"""
import hashlib
import hmac
from typing import Tuple
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend


class CryptoProvider:
    """Provides cryptographic signing and verification operations."""

    @staticmethod
    def hash_sha256(data: bytes) -> str:
        """
        Compute SHA256 hash of data.

        Args:
            data: Bytes to hash

        Returns:
            Hex-encoded SHA256 hash
        """
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def hash_chain(prev_hash: str, current_data: bytes) -> str:
        """
        Create a hash chain link (for audit log integrity).

        Args:
            prev_hash: Previous hash in the chain
            current_data: Current event data to hash

        Returns:
            New hash that incorporates previous hash
        """
        combined = (prev_hash + CryptoProvider.hash_sha256(current_data)).encode()
        return CryptoProvider.hash_sha256(combined)

    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        """
        Generate ED25519 keypair for signing.

        Returns:
            Tuple of (private_key_pem, public_key_pem)
        """
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        return private_pem, public_pem

    @staticmethod
    def sign(private_key_pem: str, data: bytes) -> str:
        """
        Sign data with ED25519 private key.

        Args:
            private_key_pem: PEM-encoded private key
            data: Data to sign

        Returns:
            Hex-encoded signature
        """
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None,
            backend=default_backend()
        )
        signature = private_key.sign(data)
        return signature.hex()

    @staticmethod
    def verify(public_key_pem: str, data: bytes, signature_hex: str) -> bool:
        """
        Verify data with ED25519 public key.

        Args:
            public_key_pem: PEM-encoded public key
            data: Original data
            signature_hex: Hex-encoded signature

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            public_key.verify(bytes.fromhex(signature_hex), data)
            return True
        except Exception:
            return False
