"""
Face alignment helpers.
"""
from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np


def align_face_crop(
    image_bgr: np.ndarray,
    bbox: Tuple[float, float, float, float],
    output_size: int = 112,
    margin: float = 0.20,
) -> Optional[np.ndarray]:
    """
    Align/crop a face region from a frame and resize to a canonical square.

    This is a lightweight alignment fallback used when a model-specific
    alignment transform is unavailable.
    """
    if image_bgr is None or image_bgr.size == 0:
        return None

    h, w = image_bgr.shape[:2]
    x1, y1, x2, y2 = bbox
    bw = max(1.0, x2 - x1)
    bh = max(1.0, y2 - y1)

    mx = bw * margin
    my = bh * margin

    ix1 = int(max(0, x1 - mx))
    iy1 = int(max(0, y1 - my))
    ix2 = int(min(w, x2 + mx))
    iy2 = int(min(h, y2 + my))

    if ix2 <= ix1 or iy2 <= iy1:
        return None

    crop = image_bgr[iy1:iy2, ix1:ix2]
    if crop.size == 0:
        return None

    return cv2.resize(crop, (output_size, output_size), interpolation=cv2.INTER_AREA)
