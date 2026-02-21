"""
Authentication policy engine.
"""
from dataclasses import dataclass
from typing import List, Optional
from .models import AuthSession
from .reasons import ReasonCode


@dataclass
class AuthDecision:
    """Represents an authentication decision."""
    decision: str  # "allow" or "deny"
    reason_codes: List[str]
    liveness_passed: bool
    similarity_score: Optional[float] = None

    def to_dict(self):
        """Convert to dictionary for JSON response."""
        return {
            "decision": self.decision,
            "reason_codes": self.reason_codes,
            "liveness_passed": self.liveness_passed,
            "similarity_score": self.similarity_score,
        }


class PolicyEngine:
    """Evaluates authentication sessions against policy rules."""

    def __init__(self):
        self.require_liveness = True
        self.similarity_threshold = 0.85  # For future template matching

    def evaluate(self, session: AuthSession) -> AuthDecision:
        """
        Evaluate an authentication session and return a decision.

        Returns:
            AuthDecision with decision ("allow" or "deny") and reason codes.
        """
        reason_codes: List[str] = []

        # Check if session is expired
        if session.is_expired():
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.SESSION_EXPIRED],
                liveness_passed=False,
            )

        # Check if session is already finished
        if session.finished:
            if session.decision == "allow":
                return AuthDecision(
                    decision="allow",
                    reason_codes=[ReasonCode.SUCCESS],
                    liveness_passed=session.liveness_passed,
                    similarity_score=session.similarity_score,
                )
            else:
                return AuthDecision(
                    decision="deny",
                    reason_codes=session.reason_codes,
                    liveness_passed=False,
                )

        # Check if all challenges are completed
        if not session.all_challenges_completed():
            return AuthDecision(
                decision="deny",
                reason_codes=[ReasonCode.LIVENESS_FAILED],
                liveness_passed=False,
            )

        # Evaluate liveness requirement
        if self.require_liveness:
            if not session.liveness_passed:
                return AuthDecision(
                    decision="deny",
                    reason_codes=[ReasonCode.LIVENESS_FAILED],
                    liveness_passed=False,
                )

        # All checks passed
        return AuthDecision(
            decision="allow",
            reason_codes=[ReasonCode.LIVENESS_PASSED],
            liveness_passed=True,
            similarity_score=session.similarity_score,
        )
