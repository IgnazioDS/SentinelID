"""
Domain models for authentication and liveness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional
import time


class ChallengeType(str, Enum):
    """Types of liveness challenges."""
    BLINK = "blink"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"


@dataclass
class Challenge:
    """Represents a single challenge in a session."""
    challenge_type: ChallengeType
    started_at: float = field(default_factory=time.time)
    timeout_seconds: int = 10
    completed: bool = False
    passed: bool = False

    def is_expired(self) -> bool:
        """Check if challenge has timed out."""
        return time.time() - self.started_at > self.timeout_seconds


@dataclass
class AuthSession:
    """
    Represents an authentication session, including optional step-up state.

    Fields added in v0.7
    --------------------
    risk_score:
        Accumulated risk score (max over all scored frames) in [0, 1].
    risk_reasons:
        Reason codes emitted by the risk scorer during the session.
    landmark_history:
        Ordered list of landmark arrays from processed frames.  Used by the
        temporal-jitter heuristic.  Not serialised; in-memory only.
    step_up_count:
        Number of step-up rounds issued so far.
    step_up_challenges:
        Additional liveness challenges generated for the step-up round.
    step_up_challenge_index:
        Index of the current challenge within step_up_challenges.
    in_step_up:
        True while the session is in the step-up challenge phase.
    """

    session_id: str
    challenges: List[Challenge] = field(default_factory=list)
    current_challenge_index: int = 0
    created_at: float = field(default_factory=time.time)
    session_timeout_seconds: int = 120
    finished: bool = False
    decision: Optional[str] = None
    reason_codes: List[str] = field(default_factory=list)
    liveness_passed: bool = False
    similarity_score: Optional[float] = None
    frame_count: int = 0  # incremented on each /auth/frame call
    latest_embedding: Optional[Any] = None
    latest_quality_reasons: List[str] = field(default_factory=list)

    # --- v0.7: risk scoring ---
    risk_score: float = 0.0
    risk_reasons: List[str] = field(default_factory=list)
    landmark_history: List[Any] = field(default_factory=list)  # not serialised

    # --- v0.7: step-up flow ---
    step_up_count: int = 0
    step_up_challenges: List[Challenge] = field(default_factory=list)
    step_up_challenge_index: int = 0
    in_step_up: bool = False

    # -----------------------------------------------------------------------
    # Session lifecycle
    # -----------------------------------------------------------------------

    def is_expired(self) -> bool:
        """Check if session has timed out."""
        return time.time() - self.created_at > self.session_timeout_seconds

    # -----------------------------------------------------------------------
    # Primary challenge helpers
    # -----------------------------------------------------------------------

    def get_current_challenge(self) -> Optional[Challenge]:
        """Return the active primary challenge, or None if all are complete."""
        if self.current_challenge_index >= len(self.challenges):
            return None
        return self.challenges[self.current_challenge_index]

    def has_next_challenge(self) -> bool:
        """Return True if another primary challenge is available."""
        return self.current_challenge_index < len(self.challenges) - 1

    def move_to_next_challenge(self) -> bool:
        """Advance to the next primary challenge. Returns True on success."""
        if self.has_next_challenge():
            self.current_challenge_index += 1
            return True
        return False

    def all_challenges_completed(self) -> bool:
        """Return True when all primary challenges are marked completed."""
        return all(c.completed for c in self.challenges)

    # -----------------------------------------------------------------------
    # Step-up challenge helpers
    # -----------------------------------------------------------------------

    def get_current_step_up_challenge(self) -> Optional[Challenge]:
        """Return the active step-up challenge, or None if all are complete."""
        if self.step_up_challenge_index >= len(self.step_up_challenges):
            return None
        return self.step_up_challenges[self.step_up_challenge_index]

    def has_next_step_up_challenge(self) -> bool:
        """Return True if another step-up challenge is available."""
        return self.step_up_challenge_index < len(self.step_up_challenges) - 1

    def move_to_next_step_up_challenge(self) -> bool:
        """Advance to the next step-up challenge. Returns True on success."""
        if self.has_next_step_up_challenge():
            self.step_up_challenge_index += 1
            return True
        return False

    def all_step_up_challenges_completed(self) -> bool:
        """Return True when all step-up challenges are marked completed."""
        return bool(self.step_up_challenges) and all(
            c.completed for c in self.step_up_challenges
        )

    def start_step_up(self, challenges: List[Challenge]) -> None:
        """Enter step-up mode with a fresh set of challenges."""
        self.step_up_challenges = challenges
        self.step_up_challenge_index = 0
        self.step_up_count += 1
        self.in_step_up = True

    def clear_step_up(self) -> None:
        """Exit step-up mode after a final decision is produced."""
        self.in_step_up = False
        self.step_up_challenges = []
        self.step_up_challenge_index = 0
