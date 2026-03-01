"""Enrollment session state and processing pipeline."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from ...core.config import settings
from ...domain.reasons import ReasonCode
from ..storage.repo_templates import TemplateRepository
from ..vision.embedder import FaceEmbedder, aggregate_embeddings
from ..vision.quality import FaceQualityGate
from ..vision.detector import FaceDetector, ModelUnavailableError


@dataclass
class EnrollmentSession:
    session_id: str
    created_at: float = field(default_factory=time.time)
    timeout_seconds: int = settings.ENROLL_SESSION_TIMEOUT_SECONDS
    target_frames: int = settings.ENROLL_TARGET_FRAMES
    embeddings: List[np.ndarray] = field(default_factory=list)
    last_reason_codes: List[str] = field(default_factory=list)
    last_quality_metrics: Dict[str, object] = field(default_factory=dict)

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.timeout_seconds

    @property
    def accepted_frames(self) -> int:
        return len(self.embeddings)


class EnrollmentSessionStore:
    """In-memory enrollment sessions (no raw frame persistence)."""

    def __init__(self, timeout_seconds: int = settings.ENROLL_SESSION_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds
        self._sessions: Dict[str, EnrollmentSession] = {}

    def create_session(self, target_frames: int = settings.ENROLL_TARGET_FRAMES) -> EnrollmentSession:
        session = EnrollmentSession(
            session_id=str(uuid.uuid4()),
            timeout_seconds=self.timeout_seconds,
            target_frames=max(1, int(target_frames)),
        )
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[EnrollmentSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        if session.is_expired():
            self._sessions.pop(session_id, None)
            return None
        return session

    def save_session(self, session: EnrollmentSession) -> None:
        self._sessions[session.session_id] = session

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


class EnrollmentPipeline:
    """Coordinates detection, quality gates, and embedding extraction for enrollment."""

    def __init__(
        self,
        detector: Optional[FaceDetector] = None,
        embedder: Optional[FaceEmbedder] = None,
        quality_gate: Optional[FaceQualityGate] = None,
    ) -> None:
        self.detector = detector or FaceDetector()
        self.embedder = embedder or FaceEmbedder(self.detector)
        self.quality_gate = quality_gate or FaceQualityGate()

    def process_frame(self, session: EnrollmentSession, frame_data: str) -> dict:
        faces, meta = self.detector.detect_faces(frame_data)
        image = meta.get("image_bgr")
        if meta.get("model_unavailable") and not meta.get("fallback_used"):
            session.last_reason_codes = [ReasonCode.MODEL_UNAVAILABLE]
            session.last_quality_metrics = {"num_faces": 0}
            return {
                "accepted": False,
                "reason_codes": session.last_reason_codes,
                "quality": session.last_quality_metrics,
                "accepted_frames": session.accepted_frames,
                "target_frames": session.target_frames,
            }

        if image is None:
            session.last_reason_codes = [ReasonCode.NO_FACE]
            session.last_quality_metrics = {"num_faces": 0}
            return {
                "accepted": False,
                "reason_codes": session.last_reason_codes,
                "quality": session.last_quality_metrics,
                "accepted_frames": session.accepted_frames,
                "target_frames": session.target_frames,
            }

        quality = self.quality_gate.evaluate(image, faces)
        if not quality.passed:
            session.last_reason_codes = list(quality.reason_codes)
            session.last_quality_metrics = dict(quality.metrics)
            return {
                "accepted": False,
                "reason_codes": session.last_reason_codes,
                "quality": session.last_quality_metrics,
                "accepted_frames": session.accepted_frames,
                "target_frames": session.target_frames,
            }

        try:
            embedding = self.embedder.extract_embedding(
                frame_data,
                face=faces[0],
                image_bgr=image,
            )
        except ModelUnavailableError:
            session.last_reason_codes = [ReasonCode.MODEL_UNAVAILABLE]
            session.last_quality_metrics = dict(quality.metrics)
            return {
                "accepted": False,
                "reason_codes": session.last_reason_codes,
                "quality": session.last_quality_metrics,
                "accepted_frames": session.accepted_frames,
                "target_frames": session.target_frames,
            }
        if embedding is None:
            session.last_reason_codes = [ReasonCode.LOW_QUALITY]
            session.last_quality_metrics = dict(quality.metrics)
            return {
                "accepted": False,
                "reason_codes": session.last_reason_codes,
                "quality": session.last_quality_metrics,
                "accepted_frames": session.accepted_frames,
                "target_frames": session.target_frames,
            }

        session.embeddings.append(np.asarray(embedding, dtype=np.float32))
        if getattr(self.embedder, "last_fallback_used", False):
            session.last_reason_codes = [ReasonCode.FALLBACK_EMBEDDING_USED]
        else:
            session.last_reason_codes = []
        session.last_quality_metrics = dict(quality.metrics)
        return {
            "accepted": True,
            "reason_codes": list(session.last_reason_codes),
            "quality": session.last_quality_metrics,
            "accepted_frames": session.accepted_frames,
            "target_frames": session.target_frames,
        }

    def build_template(self, session: EnrollmentSession) -> np.ndarray:
        if session.accepted_frames < session.target_frames:
            raise ValueError(ReasonCode.ENROLL_INCOMPLETE)
        return aggregate_embeddings(session.embeddings)

    @staticmethod
    def commit_template(
        session: EnrollmentSession,
        label: str,
        repo: TemplateRepository,
    ) -> tuple[str, np.ndarray]:
        template = aggregate_embeddings(session.embeddings)
        # Single-user product: replace previous template with newest one.
        repo.delete_all_templates()
        template_id = repo.store_template(label=label, embedding=template)
        return template_id, template
