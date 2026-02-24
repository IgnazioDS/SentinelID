"""
Tests for cloud signature verification.
"""
import pytest
import json
from sentinelid_edge.services.security.crypto import CryptoProvider
from api.signature_verifier import SignatureVerifier


class TestSignatureVerification:
    """Test signature verification in cloud ingest."""

    def test_event_signature_valid(self):
        """Test verifying valid event signature."""
        # Generate keypair
        private_pem, public_pem = CryptoProvider.generate_keypair()

        # Create payload
        payload = {
            "event_id": "test-1",
            "device_id": "device-1",
            "timestamp": 1234567890,
            "event_type": "auth_finished",
            "outcome": "allow",
            "reason_codes": ["TEST"]
        }

        # Sign payload
        payload_json = json.dumps(payload, sort_keys=True)
        signature = CryptoProvider.sign(private_pem, payload_json.encode())

        # Verify signature
        is_valid = SignatureVerifier.verify_event(public_pem, payload, signature)
        assert is_valid is True

    def test_event_signature_invalid(self):
        """Test verifying invalid event signature."""
        # Generate keypair
        private_pem, public_pem = CryptoProvider.generate_keypair()

        # Create payload
        payload = {
            "event_id": "test-1",
            "device_id": "device-1",
            "timestamp": 1234567890,
            "event_type": "auth_finished",
            "outcome": "allow",
            "reason_codes": ["TEST"]
        }

        # Create invalid signature
        invalid_signature = "0" * 128

        # Verify should fail
        is_valid = SignatureVerifier.verify_event(public_pem, payload, invalid_signature)
        assert is_valid is False

    def test_event_signature_tampered_payload(self):
        """Test signature verification fails if payload tampered."""
        # Generate keypair
        private_pem, public_pem = CryptoProvider.generate_keypair()

        # Create payload
        payload = {
            "event_id": "test-1",
            "device_id": "device-1",
            "timestamp": 1234567890,
            "event_type": "auth_finished",
            "outcome": "allow",
            "reason_codes": ["TEST"]
        }

        # Sign payload
        payload_json = json.dumps(payload, sort_keys=True)
        signature = CryptoProvider.sign(private_pem, payload_json.encode())

        # Tamper with payload
        tampered_payload = {
            "event_id": "test-1",
            "device_id": "device-1",
            "timestamp": 1234567890,
            "event_type": "auth_finished",
            "outcome": "deny",  # Changed
            "reason_codes": ["TEST"]
        }

        # Verify should fail
        is_valid = SignatureVerifier.verify_event(public_pem, tampered_payload, signature)
        assert is_valid is False

    def test_batch_signature_valid(self):
        """Test verifying valid batch signature."""
        # Generate keypair
        private_pem, public_pem = CryptoProvider.generate_keypair()

        # Create batch payload
        payload = {
            "batch_id": "batch-1",
            "device_id": "device-1",
            "timestamp": 1234567890,
            "event_count": 2,
            "event_ids": ["event-1", "event-2"]
        }

        # Sign payload
        payload_json = json.dumps(payload, sort_keys=True)
        signature = CryptoProvider.sign(private_pem, payload_json.encode())

        # Verify signature
        is_valid = SignatureVerifier.verify_batch(public_pem, payload, signature)
        assert is_valid is True

    def test_batch_signature_invalid(self):
        """Test verifying invalid batch signature."""
        # Generate keypair
        _, public_pem = CryptoProvider.generate_keypair()

        # Create batch payload
        payload = {
            "batch_id": "batch-1",
            "device_id": "device-1",
            "timestamp": 1234567890,
            "event_count": 2,
            "event_ids": ["event-1", "event-2"]
        }

        # Create invalid signature
        invalid_signature = "0" * 128

        # Verify should fail
        is_valid = SignatureVerifier.verify_batch(public_pem, payload, invalid_signature)
        assert is_valid is False

    def test_signature_verification_different_keys(self):
        """Test signature from one key fails with another key."""
        # Generate two keypairs
        private_pem1, public_pem1 = CryptoProvider.generate_keypair()
        _, public_pem2 = CryptoProvider.generate_keypair()

        # Create payload and sign with first key
        payload = {
            "event_id": "test-1",
            "device_id": "device-1",
            "timestamp": 1234567890,
            "event_type": "auth_finished",
            "outcome": "allow",
            "reason_codes": ["TEST"]
        }

        payload_json = json.dumps(payload, sort_keys=True)
        signature = CryptoProvider.sign(private_pem1, payload_json.encode())

        # Verify with first key should pass
        is_valid1 = SignatureVerifier.verify_event(public_pem1, payload, signature)
        assert is_valid1 is True

        # Verify with second key should fail
        is_valid2 = SignatureVerifier.verify_event(public_pem2, payload, signature)
        assert is_valid2 is False

    def test_canonical_json_ordering(self):
        """Test signature verification is order-independent for JSON."""
        # Generate keypair
        private_pem, public_pem = CryptoProvider.generate_keypair()

        # Create two payloads with different key order
        payload1 = {
            "event_id": "test-1",
            "device_id": "device-1",
            "timestamp": 1234567890,
        }

        payload2 = {
            "timestamp": 1234567890,
            "device_id": "device-1",
            "event_id": "test-1",
        }

        # Sign first payload
        payload_json = json.dumps(payload1, sort_keys=True)
        signature = CryptoProvider.sign(private_pem, payload_json.encode())

        # Should verify against second payload (same canonical form)
        is_valid = SignatureVerifier.verify_event(public_pem, payload2, signature)
        assert is_valid is True
