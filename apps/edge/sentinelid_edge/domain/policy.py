"""
Authentication policy engine with similarity + liveness + risk step-up.

Decision logic:
    no enrolled template               -> deny  (NOT_ENROLLED)
    liveness not passed                -> deny  (LIVENESS_FAILED)
    similarity below threshold         -> deny  (SIMILARITY_BELOW_THRESHOLD)
    risk >= R2                         -> deny  (RISK_HIGH)
    R1 <= risk < R2, step-ups left     -> step_up
    otherwise                          -> allow
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .models import AuthSession
from .reasons import ReasonCode

# Reason codes that may be forwarded from the risk scorer to the decision
_SPOOF_REASON_CODES = frozenset({
    ReasonCode.SPOOF_SUSPECT_SCREEN,
    ReasonCode.SPOOF_SUSPECT_TEMPORAL,
    ReasonCode.SPOOF_SUSPECT_BOUNDARY,
})


@dataclass
class AuthDecision:
    """Represents an authentication decision."""

    decision: str  # "allow", "deny", or "step_up"
    reason_codes: List[str]
    liveness_passed: bool
    similarity_score: Optional[float] = None
    risk_score: Optional[float] = None
    risk_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to JSON-serialisable dictionary."""
        return {
            "decision": self.decision,
            "reason_codes": self.reason_codes,
            "liveness_passed": self.liveness_passed,
            "similarity_score": self.similarity_score,
            "risk_score": self.risk_score,
            "risk_reasons": self.risk_reasons,
        }


class PolicyEngine:
    """
    Evaluates authentication sessions against liveness and risk policy.

    Parameters
    ----------
    require_liveness:
        Enforce that all liveness challenges must be passed.
    similarity_threshold:
        Minimum cosine similarity for face verification.
    risk_threshold_r1:
        Lower risk threshold.  risk >= R1 triggers step-up (if step-ups remain).
    risk_threshold_r2:
        Upper risk threshold.  risk >= R2 triggers immediate denial.
    max_step_ups:
        Maximum number of step-up rounds per session.
    """

    def __init__(
        self,
        require_liveness: bool = True,
        similarity_threshold: float = 0.85,
        risk_threshold_r1: float = 0.45,
        risk_threshold_r2: float = 0.75,
        max_step_ups: int = 1,
    ) -> None:
        self.require_liveness = require_liveness
        self.similarity_threshold = similarity_threshold
        self.risk_threshold_r1 = risk_threshold_r1
        self.risk_threshold_r2 = risk_threshold_r2
        self.max_step_ups = max_step_ups

    def evaluate(
        self,
        session: AuthSession,
        risk_score: Optional[float] = None,
        risk_reasons: Optional[List[str]] = None,
        template_enrolled: bool = True,
        similarity_score: Optional[float] = None,
        enforce_similarity: bool = False,
        force_final: bool = False,
    ) -> AuthDecision:
        """
        Evaluate an auth session and return a decision.

        Parameters
        ----------
        session:
            The authentication session to evaluate.
        risk_score:
            Combined risk score from RiskScorer (0 = safe, 1 = high risk).
            Defaults to 0.0 when not provided.
        risk_reasons:
            Reason codes emitted by heuristics (SPOOF_SUSPECT_* codes).
        template_enrolled:
            Whether a biometric template is available for matching.
        similarity_score:
            Cosine similarity between current probe and enrolled template.
        enforce_similarity:
            When True, apply template + similarity precedence checks.
        force_final:
            When True, never return "step_up" regardless of risk score.
            Used for the second /finish call after step-up challenges complete.

        Returns
        -------
        AuthDecision with decision "allow", "deny", or "step_up".
        """
        effective_risk = float(risk_score) if risk_score is not None else 0.0
        spoof_reasons = [r for r in (risk_reasons or []) if r in _SPOOF_REASON_CODES]

        # --- Session guard: expiry ---
        if session.is_expired():
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.SESSION_EXPIRED],
                liveness_passed=False,
                risk_score=effective_risk,
                risk_reasons=spoof_reasons,
            )

        # --- Session guard: already finished (idempotent re-read) ---
        if session.finished:
            if session.decision == "allow":
                return AuthDecision(
                    decision="allow",
                    reason_codes=[ReasonCode.SUCCESS],
                    liveness_passed=session.liveness_passed,
                    similarity_score=session.similarity_score,
                    risk_score=effective_risk,
                    risk_reasons=spoof_reasons,
                )
            return AuthDecision(
                decision="deny",
                reason_codes=list(session.reason_codes),
                liveness_passed=False,
                risk_score=effective_risk,
                risk_reasons=spoof_reasons,
            )

        # --- Verification guard: must have enrolled template ---
        if enforce_similarity and not template_enrolled:
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.NOT_ENROLLED],
                liveness_passed=session.liveness_passed,
                similarity_score=similarity_score,
                risk_score=effective_risk,
                risk_reasons=spoof_reasons,
            )

        # --- Liveness gate: all required challenges must be completed ---
        if session.in_step_up:
            challenges_done = (
                session.all_challenges_completed()
                and session.all_step_up_challenges_completed()
            )
        else:
            challenges_done = session.all_challenges_completed()

        if not challenges_done:
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.LIVENESS_FAILED],
                liveness_passed=False,
                similarity_score=similarity_score,
                risk_score=effective_risk,
                risk_reasons=spoof_reasons,
            )

        if self.require_liveness and not session.liveness_passed:
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.LIVENESS_FAILED],
                liveness_passed=False,
                similarity_score=similarity_score,
                risk_score=effective_risk,
                risk_reasons=spoof_reasons,
            )

        # --- Similarity gate: verification must pass before risk policy ---
        if enforce_similarity and (similarity_score is None or similarity_score < self.similarity_threshold):
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.SIMILARITY_BELOW_THRESHOLD],
                liveness_passed=session.liveness_passed,
                similarity_score=similarity_score,
                risk_score=effective_risk,
                risk_reasons=spoof_reasons,
            )

        # --- Risk gate: deny immediately if risk >= R2 ---
        if effective_risk >= self.risk_threshold_r2:
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.RISK_HIGH] + spoof_reasons,
                liveness_passed=session.liveness_passed,
                similarity_score=similarity_score,
                risk_score=effective_risk,
                risk_reasons=spoof_reasons,
            )

        # --- Risk gate: step-up if R1 <= risk < R2 and budget remaining ---
        if not force_final and effective_risk >= self.risk_threshold_r1:
            if session.step_up_count < self.max_step_ups:
                return AuthDecision(
                    decision="step_up",
                    reason_codes=[ReasonCode.RISK_STEP_UP] + spoof_reasons,
                    liveness_passed=session.liveness_passed,
                    similarity_score=similarity_score,
                    risk_score=effective_risk,
                    risk_reasons=spoof_reasons,
                )
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.MAX_STEP_UPS_REACHED] + spoof_reasons,
                liveness_passed=False,
                similarity_score=similarity_score,
                risk_score=effective_risk,
                risk_reasons=spoof_reasons,
            )

        # --- All checks passed ---
        return AuthDecision(
            decision="allow",
            reason_codes=[ReasonCode.LIVENESS_PASSED],
            liveness_passed=True,
            similarity_score=similarity_score,
            risk_score=effective_risk,
            risk_reasons=spoof_reasons,
        )
