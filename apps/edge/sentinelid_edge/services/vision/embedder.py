"""
Face embedding extraction and similarity utilities.
"""
from __future__ import annotations

from typing import Iterable, Optional

import cv2
import numpy as np

from ...core.config import settings
from .align import align_face_crop
from .detector import DetectedFace, FaceDetector, ModelUnavailableError


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm < 1e-9:
        return arr
    return arr / norm


def aggregate_embeddings(embeddings: Iterable[np.ndarray]) -> np.ndarray:
    """
    Build a stable template by mean-pooling and L2-normalization.
    """
    vectors = [l2_normalize(np.asarray(e, dtype=np.float32)) for e in embeddings]
    if not vectors:
        raise ValueError("No embeddings to aggregate")
    mean = np.mean(np.stack(vectors, axis=0), axis=0)
    return l2_normalize(mean)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    va = l2_normalize(np.asarray(a, dtype=np.float32))
    vb = l2_normalize(np.asarray(b, dtype=np.float32))
    if va.size == 0 or vb.size == 0:
        return 0.0
    if va.shape != vb.shape:
        raise ValueError("Embedding dimensionality mismatch")
    return float(np.clip(np.dot(va, vb), -1.0, 1.0))


class FaceEmbedder:
    """
    Extract embeddings using InsightFace output when available.

    Fallback embeddings are deterministic and derived from aligned pixel
    statistics for local dev/test workflows.
    """

    def __init__(
        self,
        detector: Optional[FaceDetector] = None,
        allow_fallback: Optional[bool] = None,
    ) -> None:
        self._detector = detector or FaceDetector()
        self._allow_fallback_override = allow_fallback
        self.last_fallback_used: bool = False

    def _fallback_allowed(self) -> bool:
        if self._allow_fallback_override is not None:
            return bool(self._allow_fallback_override)
        return settings.EDGE_ENV.lower() == "dev" and bool(settings.ALLOW_FALLBACK_EMBEDDINGS)

    def extract_embedding(
        self,
        frame_data: str,
        face: Optional[DetectedFace] = None,
        image_bgr: Optional[np.ndarray] = None,
    ) -> Optional[np.ndarray]:
        self.last_fallback_used = False

        if face is not None and face.embedding is not None:
            return l2_normalize(face.embedding)

        image = image_bgr if image_bgr is not None else self._detector.decode_frame_to_bgr(frame_data)
        if image is None:
            return None
        if face is None:
            faces, meta = self._detector.detect_faces(frame_data)
            if len(faces) != 1:
                if meta.get("model_unavailable"):
                    raise ModelUnavailableError("Face model unavailable for embedding extraction")
                return None
            face = faces[0]
        if not self._fallback_allowed():
            raise ModelUnavailableError("Face model unavailable for embedding extraction")
        self.last_fallback_used = True
        return self._fallback_embedding(image, face)

    def _fallback_embedding(self, image_bgr: np.ndarray, face: DetectedFace) -> Optional[np.ndarray]:
        aligned = align_face_crop(image_bgr, face.bbox, output_size=112, margin=0.18)
        if aligned is None:
            return None

        gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        dct = cv2.dct(gray)
        dct_block = dct[:16, :16].reshape(-1)

        hist = cv2.calcHist([(gray * 255.0).astype(np.uint8)], [0], None, [64], [0, 256]).reshape(-1)
        hist = hist / max(float(hist.sum()), 1.0)

        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad = cv2.magnitude(gx, gy)
        grad_stats = np.array(
            [
                float(np.mean(grad)),
                float(np.std(grad)),
                float(np.percentile(grad, 90)),
                float(np.percentile(grad, 95)),
            ],
            dtype=np.float32,
        )

        feature = np.concatenate([dct_block, hist.astype(np.float32), grad_stats], axis=0).astype(np.float32)
        # Pad/truncate to a fixed size for template compatibility.
        dim = 512
        if feature.size < dim:
            feature = np.pad(feature, (0, dim - feature.size))
        else:
            feature = feature[:dim]
        return l2_normalize(feature.astype(np.float32))
