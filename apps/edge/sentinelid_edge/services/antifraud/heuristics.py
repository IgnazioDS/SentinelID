"""
Passive anti-spoof heuristics for risk scoring.

Each function is an independent, explainable signal extractor.  No heavy ML
model is required.  Each returns (score: float in [0, 1], reason_code: str | None).
A score of 0 means no suspicion; 1 means maximum suspicion.

Heuristics implemented:
    screen_moire_score   -- FFT peak pattern detection for screen replay
    boundary_blur_score  -- Sharpness uniformity across face boundary
    temporal_jitter_score -- Landmark motion analysis (static or erratic source)
"""
from __future__ import annotations

import base64
import io
import logging
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decode_frame_to_gray(frame_data) -> Optional[np.ndarray]:
    """
    Decode a base64-encoded JPEG/PNG frame to a float32 grayscale numpy array.
    Returns None if decoding fails or PIL is unavailable.
    """
    try:
        if isinstance(frame_data, str):
            if "," in frame_data:
                _, data = frame_data.split(",", 1)
            else:
                data = frame_data
            raw = base64.b64decode(data)
        elif isinstance(frame_data, (bytes, bytearray)):
            raw = bytes(frame_data)
        else:
            return None

        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw)).convert("L")
            return np.array(img, dtype=np.float32)
        except ImportError:
            logger.debug("PIL not available; image-based heuristics return neutral scores")
            return None
    except Exception:
        return None


def _laplacian_variance(patch: np.ndarray) -> float:
    """
    Estimate sharpness as the variance of the discrete Laplacian of a 2-D patch.
    Higher values = sharper region.  Implemented without scipy.
    """
    if patch.ndim != 2 or patch.shape[0] < 3 or patch.shape[1] < 3:
        return float(np.var(patch)) if patch.size > 0 else 0.0

    kernel = np.array([[0.0, 1.0, 0.0],
                        [1.0, -4.0, 1.0],
                        [0.0, 1.0, 0.0]], dtype=np.float32)

    ph, pw = patch.shape
    result = np.zeros((ph - 2, pw - 2), dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            result += kernel[dy, dx] * patch[dy: dy + ph - 2, dx: dx + pw - 2]
    return float(np.var(result))


# ---------------------------------------------------------------------------
# Heuristic 1: Screen / Moire detection via FFT
# ---------------------------------------------------------------------------

def screen_moire_score(frame_data) -> Tuple[float, Optional[str]]:
    """
    Detect Moire pattern artefacts that appear when a camera photographs a
    screen.  Screens emit images at a fixed pixel pitch.  When photographed,
    the pixel grid creates periodic frequency components in the FFT magnitude
    spectrum that concentrate energy in the mid-frequency annulus relative to
    the outer (high-frequency) region.

    Returns:
        (score, reason_code) where score in [0, 1].
        reason_code = 'SPOOF_SUSPECT_SCREEN' when score > 0.3, else None.
    """
    gray = _decode_frame_to_gray(frame_data)
    if gray is None:
        return 0.0, None

    try:
        h, w = gray.shape
        if h < 32 or w < 32:
            return 0.0, None

        fft_shifted = np.fft.fftshift(np.fft.fft2(gray))
        power = np.log1p(np.abs(fft_shifted))

        cy, cx = h // 2, w // 2
        ys, xs = np.ogrid[:h, :w]
        dist = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)

        # Mid-frequency annulus: radius consistent with screen pixel pitch
        r_inner = min(h, w) // 8
        r_outer = min(h, w) // 3

        annulus_mask = (dist >= r_inner) & (dist <= r_outer)
        outer_mask = dist > r_outer

        if not annulus_mask.any() or not outer_mask.any():
            return 0.0, None

        annulus_energy = float(np.mean(power[annulus_mask]))
        outer_energy = float(np.mean(power[outer_mask]))

        if outer_energy < 1e-6:
            return 0.0, None

        # Screens concentrate energy in mid-frequencies; genuine faces are flatter
        mid_to_outer_ratio = annulus_energy / (outer_energy + 1e-6)

        # Empirical calibration: natural ratio ~1.2-2.0, screens ~2.5+
        score = float(np.clip((mid_to_outer_ratio - 2.0) / 2.0, 0.0, 1.0))
        reason = "SPOOF_SUSPECT_SCREEN" if score > 0.3 else None
        return score, reason

    except Exception:
        return 0.0, None


# ---------------------------------------------------------------------------
# Heuristic 2: Face boundary blur / sharpness uniformity
# ---------------------------------------------------------------------------

def boundary_blur_score(frame_data, landmarks) -> Tuple[float, Optional[str]]:
    """
    Detect unnatural uniformity of sharpness across the face boundary.

    A live face has 3-D depth: the nose is closer to the camera than the
    forehead or jaw.  A flat print or screen shows nearly uniform sharpness
    across the entire face.  We compare Laplacian variance at the face centre
    vs the face perimeter; a very high uniformity ratio is suspicious.

    Returns:
        (score, reason_code) where score in [0, 1].
        reason_code = 'SPOOF_SUSPECT_BOUNDARY' when score > 0.3, else None.
    """
    gray = _decode_frame_to_gray(frame_data)
    if gray is None or landmarks is None:
        return 0.0, None

    try:
        h, w = gray.shape
        lm = np.array(landmarks, dtype=np.float32)
        if lm.ndim != 2 or lm.shape[1] < 2 or len(lm) < 5:
            return 0.0, None

        xs = lm[:, 0]
        ys = lm[:, 1]
        face_cx = float(np.mean(xs))
        face_cy = float(np.mean(ys))
        face_radius = float(max(np.std(xs), np.std(ys), 10.0))

        # Central patch around nose / face centre
        cr = max(int(face_radius * 0.15), 4)
        cy_i, cx_i = int(face_cy), int(face_cx)
        y0c, y1c = max(0, cy_i - cr), min(h, cy_i + cr)
        x0c, x1c = max(0, cx_i - cr), min(w, cx_i + cr)

        center_patch = gray[y0c:y1c, x0c:x1c]
        if center_patch.size < 16:
            return 0.0, None

        center_sharpness = _laplacian_variance(center_patch)

        # Boundary ring: 70-90% of face radius from centre
        ys_grid, xs_grid = np.ogrid[:h, :w]
        dist_from_center = np.sqrt(
            (ys_grid - face_cy) ** 2 + (xs_grid - face_cx) ** 2
        )
        boundary_mask = (
            (dist_from_center >= face_radius * 0.7)
            & (dist_from_center <= face_radius * 0.9)
        )
        boundary_pixels = gray[boundary_mask]
        boundary_sharpness = float(np.var(boundary_pixels)) if boundary_pixels.size > 0 else 0.0

        denom = max(center_sharpness, boundary_sharpness) + 1e-6
        numer = min(center_sharpness, boundary_sharpness)

        # Uniformity ratio: 1.0 = perfectly uniform (suspicious), 0 = very different (natural)
        ratio = numer / denom
        score = float(np.clip((ratio - 0.7) / 0.3, 0.0, 1.0))
        reason = "SPOOF_SUSPECT_BOUNDARY" if score > 0.3 else None
        return score, reason

    except Exception:
        return 0.0, None


# ---------------------------------------------------------------------------
# Heuristic 3: Temporal landmark jitter / motion inconsistency
# ---------------------------------------------------------------------------

def temporal_jitter_score(landmark_history: List) -> Tuple[float, Optional[str]]:
    """
    Detect temporal inconsistencies in facial landmark motion.

    Genuine live faces exhibit smooth, natural motion.  Replay attacks from
    a static photo show near-zero inter-frame displacement.  Erratic sources
    (some synthetic attacks) show high coefficient of variation in displacement.

    Args:
        landmark_history: List of landmark arrays from successive frames.
                          Each element is an (N, 2) array or equivalent.

    Returns:
        (score, reason_code) where score in [0, 1].
        reason_code = 'SPOOF_SUSPECT_TEMPORAL' when score > 0.3, else None.
    """
    if not landmark_history or len(landmark_history) < 3:
        return 0.0, None

    try:
        frames: List[np.ndarray] = []
        for lm in landmark_history[-20:]:
            arr = np.array(lm, dtype=np.float32)
            if arr.ndim == 2 and arr.shape[1] >= 2:
                frames.append(arr)

        if len(frames) < 3:
            return 0.0, None

        displacements: List[float] = []
        for i in range(1, len(frames)):
            if frames[i].shape == frames[i - 1].shape:
                per_landmark = np.linalg.norm(frames[i] - frames[i - 1], axis=1)
                displacements.append(float(np.mean(per_landmark)))

        if not displacements:
            return 0.0, None

        disp_array = np.array(displacements)
        mean_disp = float(np.mean(disp_array))
        std_disp = float(np.std(disp_array))

        # Static image: near-zero mean displacement over multiple frames
        STATIC_THRESHOLD = 0.5  # pixels
        static_score = float(np.clip(1.0 - mean_disp / STATIC_THRESHOLD, 0.0, 1.0))

        # Erratic motion: very high coefficient of variation
        cov = std_disp / (mean_disp + 1e-6)
        ERRATIC_COV_THRESHOLD = 3.0
        erratic_score = float(np.clip((cov - ERRATIC_COV_THRESHOLD) / 3.0, 0.0, 1.0))

        score = max(static_score, erratic_score * 0.5)
        reason = "SPOOF_SUSPECT_TEMPORAL" if score > 0.3 else None
        return score, reason

    except Exception:
        return 0.0, None
