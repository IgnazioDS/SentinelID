"""Local threshold calibration for verification FAR/FRR tuning."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

from .detector import FaceDetector
from .embedder import FaceEmbedder, aggregate_embeddings, cosine_similarity
from .quality import FaceQualityGate
from ...domain.reasons import ReasonCode
from .detector import ModelUnavailableError

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _iter_image_files(folder: Path) -> Iterable[Path]:
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in _ALLOWED_EXTENSIONS:
            yield path


def _file_to_data_url(path: Path) -> str:
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def _extract_embedding_from_file(
    path: Path,
    detector: FaceDetector,
    embedder: FaceEmbedder,
    quality_gate: FaceQualityGate,
) -> Tuple[np.ndarray | None, List[str]]:
    frame_data = _file_to_data_url(path)
    faces, meta = detector.detect_faces(frame_data)
    image = meta.get("image_bgr")
    if image is None:
        return None, ["NO_FACE"]

    quality = quality_gate.evaluate(image, faces)
    if not quality.passed:
        return None, [code.value if hasattr(code, "value") else str(code) for code in quality.reason_codes]

    try:
        embedding = embedder.extract_embedding(frame_data, face=faces[0], image_bgr=image)
    except ModelUnavailableError:
        return None, [ReasonCode.MODEL_UNAVAILABLE.value]
    if embedding is None:
        return None, [ReasonCode.LOW_QUALITY.value]
    return embedding, []


def _distribution_stats(values: List[float]) -> Dict[str, float | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "p05": None,
            "p50": None,
            "p95": None,
        }

    arr = np.asarray(values, dtype=np.float32)
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "p05": float(np.percentile(arr, 5)),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
    }


def run_threshold_calibration(
    genuine_dir: str,
    impostor_dir: str,
    target_far: float = 0.01,
) -> Dict[str, object]:
    """
    Compute genuine/impostor similarity distributions and recommend threshold.

    No raw frame bytes are retained; report contains only aggregate metrics.
    """
    detector = FaceDetector()
    embedder = FaceEmbedder(detector)
    quality_gate = FaceQualityGate()

    genuine_root = Path(genuine_dir)
    impostor_root = Path(impostor_dir)
    if not genuine_root.exists() or not impostor_root.exists():
        raise FileNotFoundError("Calibration folders must exist")

    genuine_embeddings: List[np.ndarray] = []
    impostor_embeddings: List[np.ndarray] = []
    skipped_genuine = 0
    skipped_impostor = 0

    for path in _iter_image_files(genuine_root):
        embedding, reasons = _extract_embedding_from_file(path, detector, embedder, quality_gate)
        if embedding is None:
            skipped_genuine += 1
            continue
        genuine_embeddings.append(embedding)

    for path in _iter_image_files(impostor_root):
        embedding, reasons = _extract_embedding_from_file(path, detector, embedder, quality_gate)
        if embedding is None:
            skipped_impostor += 1
            continue
        impostor_embeddings.append(embedding)

    if len(genuine_embeddings) < 4:
        raise RuntimeError("Need at least 4 valid genuine images for calibration")
    if len(impostor_embeddings) < 1:
        raise RuntimeError("Need at least 1 valid impostor image for calibration")

    enroll_count = max(3, min(8, len(genuine_embeddings) // 2))
    enroll_embeddings = genuine_embeddings[:enroll_count]
    probe_genuine = genuine_embeddings[enroll_count:]
    if not probe_genuine:
        probe_genuine = genuine_embeddings[-1:]

    template = aggregate_embeddings(enroll_embeddings)
    genuine_scores = [cosine_similarity(template, emb) for emb in probe_genuine]
    impostor_scores = [cosine_similarity(template, emb) for emb in impostor_embeddings]

    thresholds = sorted(set(genuine_scores + impostor_scores + [-1.0, 1.0]))
    operating_points = []
    best_for_target = None
    best_eer_point = None

    for threshold in thresholds:
        far = sum(score >= threshold for score in impostor_scores) / max(len(impostor_scores), 1)
        frr = sum(score < threshold for score in genuine_scores) / max(len(genuine_scores), 1)
        point = {
            "threshold": float(threshold),
            "far": float(far),
            "frr": float(frr),
        }
        operating_points.append(point)

        if far <= target_far:
            if best_for_target is None:
                best_for_target = point
            else:
                if point["frr"] < best_for_target["frr"]:
                    best_for_target = point
                elif point["frr"] == best_for_target["frr"] and point["threshold"] > best_for_target["threshold"]:
                    best_for_target = point

        diff = abs(far - frr)
        if best_eer_point is None or diff < abs(best_eer_point["far"] - best_eer_point["frr"]):
            best_eer_point = point

    if best_for_target is None:
        # Target FAR is unattainable; pick minimum FAR point.
        best_for_target = min(operating_points, key=lambda p: (p["far"], p["frr"]))

    return {
        "target_far": float(target_far),
        "recommended_threshold": float(best_for_target["threshold"]),
        "operating_point": best_for_target,
        "approx_eer_point": best_eer_point,
        "genuine_distribution": _distribution_stats(genuine_scores),
        "impostor_distribution": _distribution_stats(impostor_scores),
        "input_counts": {
            "genuine_total_files": sum(1 for _ in _iter_image_files(genuine_root)),
            "impostor_total_files": sum(1 for _ in _iter_image_files(impostor_root)),
            "genuine_used": len(genuine_embeddings),
            "impostor_used": len(impostor_embeddings),
            "genuine_skipped": skipped_genuine,
            "impostor_skipped": skipped_impostor,
            "enroll_reference_frames": len(enroll_embeddings),
            "genuine_probe_frames": len(probe_genuine),
        },
        "operating_curve": operating_points,
    }
