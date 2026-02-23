"""
Risk scorer: single entry-point that combines passive heuristics into one
risk_score in [0, 1] and a list of triggered reason codes.

Usage:
    from sentinelid_edge.services.antifraud.risk import get_risk_scorer, get_risk_metrics

    scorer = get_risk_scorer()
    result = scorer.score_frame(frame_data, landmarks, landmark_history)
    # result.risk_score  -- float in [0, 1]
    # result.risk_reasons -- list of reason code strings

    metrics = get_risk_metrics()
    metrics.aggregated_counts()  # {"low": N, "medium": N, "high": N, "total": N}

The optional classifier stub (classifier.py) is disabled by default.  Enable
it only if a trained model artefact is present (set use_classifier=True).
"""
from __future__ import annotations

import collections
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from .heuristics import (
    screen_moire_score,
    boundary_blur_score,
    temporal_jitter_score,
)

logger = logging.getLogger(__name__)

# Weights for combining heuristic sub-scores into a single risk score.
# Must sum to 1.0.
_HEURISTIC_WEIGHTS: dict[str, float] = {
    "screen": 0.40,
    "boundary": 0.30,
    "temporal": 0.30,
}

_RISK_SCORE_WINDOW_SIZE = 100


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class RiskResult:
    """Output of RiskScorer.score_frame()."""

    risk_score: float  # combined risk score in [0, 1]
    risk_reasons: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# In-memory diagnostic metrics (no sensitive data)
# ---------------------------------------------------------------------------

class RiskMetrics:
    """
    Thread-safe in-memory ring buffer of recent risk scores for diagnostics.
    Stores only numeric scores; no frames, embeddings, or session identifiers.
    """

    def __init__(self, window_size: int = _RISK_SCORE_WINDOW_SIZE) -> None:
        self._scores: collections.deque = collections.deque(maxlen=window_size)

    def record(self, score: float) -> None:
        """Append a score to the ring buffer."""
        self._scores.append(round(float(score), 4))

    def last_n(self, n: int = 20) -> List[float]:
        """Return the most recent n scores (or all if fewer recorded)."""
        scores = list(self._scores)
        return scores[-n:] if len(scores) > n else scores

    def aggregated_counts(self) -> dict:
        """
        Return binned counts without individual values.

        Buckets:
            low    -- risk < 0.4
            medium -- 0.4 <= risk < 0.7
            high   -- risk >= 0.7
        """
        low = sum(1 for s in self._scores if s < 0.4)
        medium = sum(1 for s in self._scores if 0.4 <= s < 0.7)
        high = sum(1 for s in self._scores if s >= 0.7)
        return {"low": low, "medium": medium, "high": high, "total": len(self._scores)}

    def reset(self) -> None:
        """Clear all recorded scores (used in tests)."""
        self._scores.clear()


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_risk_metrics: Optional[RiskMetrics] = None


def get_risk_metrics() -> RiskMetrics:
    """Return the module-level RiskMetrics singleton."""
    global _risk_metrics
    if _risk_metrics is None:
        _risk_metrics = RiskMetrics()
    return _risk_metrics


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class RiskScorer:
    """
    Combines passive heuristic signals into a risk score.

    Heuristics (all enabled by default):
        screen_moire  -- FFT peak pattern for screen replay detection
        boundary_blur -- sharpness uniformity (printed photo detection)
        temporal_jitter -- landmark motion (static or erratic source)

    Optional classifier stub:
        Disabled by default (use_classifier=False).  If enabled and a trained
        AntiSpoofClassifier is importable from classifier.py, its output is
        blended 50/50 with the weighted heuristic sum.
    """

    def __init__(self, use_classifier: bool = False) -> None:
        self._use_classifier = use_classifier
        self._classifier = None
        if use_classifier:
            try:
                from .classifier import AntiSpoofClassifier  # type: ignore[import]
                self._classifier = AntiSpoofClassifier()
                logger.info("AntiSpoofClassifier loaded")
            except Exception as exc:
                logger.debug("AntiSpoofClassifier not available: %s", type(exc).__name__)

    def score_frame(
        self,
        frame_data=None,
        landmarks=None,
        landmark_history: Optional[List] = None,
    ) -> RiskResult:
        """
        Score a single frame observation.

        Args:
            frame_data: Base64-encoded image string, raw bytes, or None.
            landmarks:  Face landmark array (N x 2) from the face detector, or None.
            landmark_history: List of past landmark arrays for temporal analysis.

        Returns:
            RiskResult with risk_score in [0, 1] and triggered reason codes.
            Returns RiskResult(0.0, []) if all inputs are None.
        """
        raw_scores: dict[str, float] = {}
        reasons: List[str] = []

        # --- Heuristic 1: screen / Moire ---
        s_screen, r_screen = screen_moire_score(frame_data)
        raw_scores["screen"] = s_screen
        if r_screen:
            reasons.append(r_screen)

        # --- Heuristic 2: boundary blur uniformity ---
        s_boundary, r_boundary = boundary_blur_score(frame_data, landmarks)
        raw_scores["boundary"] = s_boundary
        if r_boundary:
            reasons.append(r_boundary)

        # --- Heuristic 3: temporal landmark jitter ---
        s_temporal, r_temporal = temporal_jitter_score(landmark_history or [])
        raw_scores["temporal"] = s_temporal
        if r_temporal:
            reasons.append(r_temporal)

        # Weighted combination of heuristic scores
        heuristic_combined = sum(
            raw_scores.get(k, 0.0) * w for k, w in _HEURISTIC_WEIGHTS.items()
        )

        # Optional classifier blend
        if self._use_classifier and self._classifier is not None:
            try:
                clf_score, clf_reasons = self._classifier.score(frame_data, landmarks)
                clf_score = float(max(0.0, min(1.0, clf_score)))
                combined = 0.5 * heuristic_combined + 0.5 * clf_score
                reasons.extend(r for r in (clf_reasons or []) if r not in reasons)
            except Exception:
                combined = heuristic_combined
        else:
            combined = heuristic_combined

        combined = float(min(max(combined, 0.0), 1.0))

        # Record for diagnostics (no sensitive content)
        get_risk_metrics().record(combined)

        # Deduplicate reasons while preserving order
        seen: set[str] = set()
        deduped: List[str] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                deduped.append(r)

        return RiskResult(risk_score=round(combined, 4), risk_reasons=deduped)


_risk_scorer: Optional[RiskScorer] = None


def get_risk_scorer() -> RiskScorer:
    """Return the module-level RiskScorer singleton."""
    global _risk_scorer
    if _risk_scorer is None:
        _risk_scorer = RiskScorer(use_classifier=False)
    return _risk_scorer
