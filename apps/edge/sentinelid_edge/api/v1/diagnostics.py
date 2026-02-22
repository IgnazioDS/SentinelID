"""
Diagnostic endpoint for monitoring edge service health and telemetry status.
"""
from fastapi import APIRouter, Depends
from sentinelid_edge.core.auth import verify_bearer_token
from sentinelid_edge.services.security.device_binding import DeviceKeychain
from sentinelid_edge.services.storage.repo_outbox import OutboxRepository
from sentinelid_edge.services.telemetry.exporter import TelemetryExporter
from typing import Dict, Any

router = APIRouter()


@router.get("/diagnostics")
async def get_diagnostics(_: str = Depends(verify_bearer_token)) -> Dict[str, Any]:
    """
    Get diagnostic information about the edge service.

    Includes device information, telemetry outbox status, and last export status.
    Requires bearer token authentication.

    Returns:
        Dictionary with diagnostic data
    """
    # Get device information
    keychain = DeviceKeychain()
    device_id = keychain.get_device_id()

    # Get outbox repository stats
    outbox = OutboxRepository()
    outbox_stats = outbox.get_stats()

    # Get DLQ events preview
    dlq_events = outbox.get_dlq_events(limit=5)
    dlq_preview = [
        {
            'id': event.id,
            'created_at': event.created_at,
            'attempts': event.attempts,
            'last_error': event.last_error
        }
        for event in dlq_events
    ]

    return {
        'device_id': device_id,
        'device_key_fingerprint': keychain.get_public_key_fingerprint()[:16],  # First 16 chars
        'outbox': {
            'pending_count': outbox_stats['pending_count'],
            'dlq_count': outbox_stats['dlq_count'],
            'sent_count': outbox_stats['sent_count']
        },
        'telemetry': {
            'last_export_attempt_time': None,  # Would be set if exporter is initialized
            'last_export_error': None
        },
        'dlq_preview': dlq_preview,
        'status': 'healthy'
    }
