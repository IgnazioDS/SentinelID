"""
Enrollment endpoints for v0.8 verification pipeline.

Flow:
    POST /enroll/start   -> create enrollment session
    POST /enroll/frame   -> validate quality + collect embedding
    POST /enroll/commit  -> aggregate stable template and store encrypted blob
    POST /enroll/reset   -> drop enrollment session
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...core.config import settings
from ...core.request_context import set_session_id
from ...domain.reasons import ReasonCode
from ...services.enrollment.sessions import (
    EnrollmentPipeline,
    EnrollmentSessionStore,
)
from ...services.storage.repo_templates import TemplateRepository
from ...services.vision.calibration import run_threshold_calibration
from ...services.vision.detector import FaceDetector
from ...services.vision.embedder import FaceEmbedder
from ...services.vision.quality import FaceQualityGate

logger = logging.getLogger(__name__)
router = APIRouter()

_template_repo: Optional[TemplateRepository] = None
_enroll_store = EnrollmentSessionStore(timeout_seconds=settings.ENROLL_SESSION_TIMEOUT_SECONDS)
_detector = FaceDetector()
_embedder = FaceEmbedder(_detector)
_quality_gate = FaceQualityGate()
_pipeline = EnrollmentPipeline(detector=_detector, embedder=_embedder, quality_gate=_quality_gate)


def _reason_values(codes: List[Any]) -> List[str]:
    values = []
    for code in codes:
        values.append(code.value if hasattr(code, "value") else str(code))
    return values


def _get_template_repo() -> TemplateRepository:
    global _template_repo
    if _template_repo is None:
        _template_repo = TemplateRepository(
            db_path=settings.DB_PATH,
            keychain_dir=settings.KEYCHAIN_DIR,
        )
    return _template_repo


class StartEnrollRequest(BaseModel):
    target_frames: int = Field(default=settings.ENROLL_TARGET_FRAMES, ge=1, le=64)


class StartEnrollResponse(BaseModel):
    session_id: str
    target_frames: int


class EnrollFrameRequest(BaseModel):
    session_id: str
    frame: str


class EnrollFrameResponse(BaseModel):
    session_id: str
    accepted: bool
    accepted_frames: int
    target_frames: int
    reason_codes: List[str] = Field(default_factory=list)
    quality: Dict[str, Any] = Field(default_factory=dict)


class CommitEnrollRequest(BaseModel):
    session_id: str
    label: str = "default"


class CommitEnrollResponse(BaseModel):
    status: str
    template_id: str
    accepted_frames: int
    target_frames: int


class ResetEnrollRequest(BaseModel):
    session_id: str


class ResetEnrollResponse(BaseModel):
    status: str
    session_id: str


class CalibrateRequest(BaseModel):
    genuine_dir: str
    impostor_dir: str
    target_far: float = Field(default=0.01, gt=0.0, le=1.0)


class CalibrateResponse(BaseModel):
    report: Dict[str, Any]


@router.post("/start", response_model=StartEnrollResponse)
async def start_enrollment(request: StartEnrollRequest) -> StartEnrollResponse:
    session = _enroll_store.create_session(target_frames=request.target_frames)
    set_session_id(session.session_id)
    return StartEnrollResponse(
        session_id=session.session_id,
        target_frames=session.target_frames,
    )


@router.post("/frame", response_model=EnrollFrameResponse)
async def enroll_frame(request: EnrollFrameRequest) -> EnrollFrameResponse:
    set_session_id(request.session_id)
    session = _enroll_store.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment session not found")

    result = _pipeline.process_frame(session, request.frame)
    result_reason_values = _reason_values(result["reason_codes"])
    if ReasonCode.MODEL_UNAVAILABLE.value in result_reason_values:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Face model unavailable",
                "reason_codes": [ReasonCode.MODEL_UNAVAILABLE.value],
            },
        )
    _enroll_store.save_session(session)
    return EnrollFrameResponse(
        session_id=session.session_id,
        accepted=bool(result["accepted"]),
        accepted_frames=int(result["accepted_frames"]),
        target_frames=int(result["target_frames"]),
        reason_codes=result_reason_values,
        quality=result["quality"],
    )


@router.post("/commit", response_model=CommitEnrollResponse)
async def commit_enrollment(request: CommitEnrollRequest) -> CommitEnrollResponse:
    set_session_id(request.session_id)
    session = _enroll_store.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment session not found")

    if session.accepted_frames < session.target_frames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "reason_codes": [ReasonCode.ENROLL_INCOMPLETE.value],
                "accepted_frames": session.accepted_frames,
                "target_frames": session.target_frames,
            },
        )

    repo = _get_template_repo()
    template_id, _template = _pipeline.commit_template(session, request.label, repo)
    _enroll_store.delete_session(session.session_id)

    return CommitEnrollResponse(
        status="enrollment_committed",
        template_id=template_id,
        accepted_frames=session.accepted_frames,
        target_frames=session.target_frames,
    )


@router.post("/reset", response_model=ResetEnrollResponse)
async def reset_enrollment(request: ResetEnrollRequest) -> ResetEnrollResponse:
    set_session_id(request.session_id)
    _enroll_store.delete_session(request.session_id)
    return ResetEnrollResponse(status="reset", session_id=request.session_id)


@router.post("/calibrate", response_model=CalibrateResponse)
async def calibrate_threshold(request: CalibrateRequest) -> CalibrateResponse:
    try:
        report = run_threshold_calibration(
            genuine_dir=request.genuine_dir,
            impostor_dir=request.impostor_dir,
            target_far=request.target_far,
        )
        return CalibrateResponse(report=report)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
