"""
Diagnostic endpoint for monitoring edge service health, telemetry status,
and risk scoring metrics.

Requires bearer token authentication.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any

from sentinelid_edge.core.auth import verify_bearer_token
from sentinelid_edge.core.config import settings
from sentinelid_edge.services.antifraud.risk import get_risk_metrics
from sentinelid_edge.services.observability.perf import get_perf_registry
from sentinelid_edge.services.processing.frame_control import get_frame_controller
from sentinelid_edge.services.security.device_binding import DeviceKeychain
from sentinelid_edge.services.storage.repo_outbox import OutboxRepository
from sentinelid_edge.services.telemetry.runtime import get_telemetry_runtime

router = APIRouter()


@router.get("/diagnostics")
async def get_diagnostics(_: str = Depends(verify_bearer_token)) -> Dict[str, Any]:
    """
    Return diagnostic information about the edge service.

    Includes:
    - Device identity summary
    - Telemetry outbox statistics
    - DLQ preview (last 5 events, no payloads)
    - Risk scoring thresholds and aggregated score counts (v0.7)

    No sensitive data (frames, embeddings, raw risk scores) is included.
    """
    # Device information
    keychain = DeviceKeychain()
    device_id = keychain.get_device_id()

    # Outbox stats
    outbox = OutboxRepository()
    outbox_stats = outbox.get_stats()

    dlq_events = outbox.get_dlq_events(limit=5)
    dlq_preview = [
        {
            "id": event.id,
            "created_at": event.created_at,
            "attempts": event.attempts,
            "last_error": event.last_error,
        }
        for event in dlq_events
    ]

    # Risk metrics: aggregated counts only (no individual scores exposed)
    risk_metrics = get_risk_metrics()
    risk_counts = risk_metrics.aggregated_counts()

    telemetry_runtime = get_telemetry_runtime()
    telemetry_stats = (
        telemetry_runtime.stats()
        if telemetry_runtime is not None
        else {
            "enabled": False,
            "queue": {"max_size": 0, "current_size": 0, "wake_signals": 0, "dropped_signals": 0},
            "loop": {
                "started_at": None,
                "iterations": 0,
                "export_errors": 0,
                "last_loop_error": None,
                "last_export_success_at": None,
            },
            "outbox": outbox_stats,
            "last_export_attempt_time": None,
            "last_export_error": None,
        }
    )

    return {
        "device_id": device_id,
        "device_key_fingerprint": keychain.get_public_key_fingerprint()[:16],
        "outbox": {
            "pending_count": outbox_stats["pending_count"],
            "dlq_count": outbox_stats["dlq_count"],
            "sent_count": outbox_stats["sent_count"],
        },
        "telemetry": telemetry_stats,
        "dlq_preview": dlq_preview,
        "risk": {
            "threshold_r1": settings.RISK_THRESHOLD_R1,
            "threshold_r2": settings.RISK_THRESHOLD_R2,
            "max_step_ups_per_session": settings.MAX_STEP_UPS_PER_SESSION,
            "score_counts": risk_counts,  # {"low": N, "medium": N, "high": N, "total": N}
        },
        "verification": {
            "similarity_threshold": settings.SIMILARITY_THRESHOLD,
            "enroll_target_frames": settings.ENROLL_TARGET_FRAMES,
            "quality_gates": {
                "min_face_size_px": settings.MIN_FACE_SIZE_PX,
                "min_blur_variance": settings.MIN_BLUR_VARIANCE,
                "min_illumination_mean": settings.MIN_ILLUMINATION_MEAN,
                "max_illumination_mean": settings.MAX_ILLUMINATION_MEAN,
                "max_abs_yaw_deg": settings.MAX_ABS_YAW_DEG,
                "max_abs_pitch_deg": settings.MAX_ABS_PITCH_DEG,
                "max_abs_roll_deg": settings.MAX_ABS_ROLL_DEG,
            },
        },
        "frame_processing": get_frame_controller().snapshot(),
        "performance": get_perf_registry().snapshot(),
        "status": "healthy",
    }
