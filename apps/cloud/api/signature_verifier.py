"""
Signature verification for cloud ingest.
"""
import json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


class SignatureVerifier:
    """Verifies ED25519 signatures from edge devices."""

    @staticmethod
    def verify_event(public_key_pem: str, payload: dict, signature_hex: str) -> bool:
        """
        Verify event signature.

        Args:
            public_key_pem: PEM-encoded ED25519 public key
            payload: Event payload dict
            signature_hex: Hex-encoded signature

        Returns:
            True if signature is valid, False otherwise
        """
        return SignatureVerifier._verify(public_key_pem, payload, signature_hex)

    @staticmethod
    def verify_batch(public_key_pem: str, payload: dict, signature_hex: str) -> bool:
        """
        Verify batch signature.

        Args:
            public_key_pem: PEM-encoded ED25519 public key
            payload: Batch payload dict
            signature_hex: Hex-encoded signature

        Returns:
            True if signature is valid, False otherwise
        """
        return SignatureVerifier._verify(public_key_pem, payload, signature_hex)

    @staticmethod
    def _verify(public_key_pem: str, payload: dict, signature_hex: str) -> bool:
        """
        Internal signature verification.

        Args:
            public_key_pem: PEM-encoded ED25519 public key
            payload: Payload dict
            signature_hex: Hex-encoded signature

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Load public key
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode('utf-8'),
                backend=default_backend()
            )

            # Create canonical JSON for verification
            payload_json = json.dumps(payload, sort_keys=True)
            data = payload_json.encode('utf-8')
            signature = bytes.fromhex(signature_hex)

            # Verify signature
            public_key.verify(signature, data)
            return True

        except Exception:
            return False
