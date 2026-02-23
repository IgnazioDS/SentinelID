"""
Authentication policy engine with risk-based step-up support.

Decision logic:
    risk < R1                          -> allow (if liveness passed)
    R1 <= risk < R2, step-ups left     -> step_up
    risk >= R2                         -> deny  (RISK_HIGH)
    liveness not passed                -> deny  (LIVENESS_FAILED)
"""
from __future__ import annotations

from dataclasses import dataclass
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

    def to_dict(self) -> dict:
        """Convert to JSON-serialisable dictionary."""
        return {
            "decision": self.decision,
            "reason_codes": self.reason_codes,
            "liveness_passed": self.liveness_passed,
            "similarity_score": self.similarity_score,
            "risk_score": self.risk_score,
        }


class PolicyEngine:
    """
    Evaluates authentication sessions against liveness and risk policy.

    Parameters
    ----------
    require_liveness:
        Enforce that all liveness challenges must be passed.
    similarity_threshold:
        Minimum cosine similarity for template matching (future use).
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
                )
            return AuthDecision(
                decision="deny",
                reason_codes=list(session.reason_codes),
                liveness_passed=False,
                risk_score=effective_risk,
            )

        # --- Risk gate: deny immediately if risk >= R2 ---
        if effective_risk >= self.risk_threshold_r2:
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.RISK_HIGH] + spoof_reasons,
                liveness_passed=session.liveness_passed,
                risk_score=effective_risk,
            )

        # --- Risk gate: step-up if R1 <= risk < R2 and budget remaining ---
        if (
            not force_final
            and effective_risk >= self.risk_threshold_r1
            and session.step_up_count < self.max_step_ups
        ):
            return AuthDecision(
                decision="step_up",
                reason_codes=[ReasonCode.RISK_STEP_UP] + spoof_reasons,
                liveness_passed=session.liveness_passed,
                risk_score=effective_risk,
            )

        # --- Liveness gate: all required challenges must be completed ---
        if session.in_step_up:
            challenges_done = session.all_step_up_challenges_completed()
        else:
            challenges_done = session.all_challenges_completed()

        if not challenges_done:
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.LIVENESS_FAILED],
                liveness_passed=False,
                risk_score=effective_risk,
            )

        if self.require_liveness and not session.liveness_passed:
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.LIVENESS_FAILED],
                liveness_passed=False,
                risk_score=effective_risk,
            )

        # --- All checks passed ---
        return AuthDecision(
            decision="allow",
            reason_codes=[ReasonCode.LIVENESS_PASSED],
            liveness_passed=True,
            similarity_score=session.similarity_score,
            risk_score=effective_risk,
        )
