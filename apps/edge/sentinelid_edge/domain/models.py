"""
Domain models for authentication and liveness.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
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
    """Represents an authentication session."""
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

    def is_expired(self) -> bool:
        """Check if session has timed out."""
        return time.time() - self.created_at > self.session_timeout_seconds

    def get_current_challenge(self) -> Optional[Challenge]:
        """Get the current challenge, or None if all are complete."""
        if self.current_challenge_index >= len(self.challenges):
            return None
        return self.challenges[self.current_challenge_index]

    def has_next_challenge(self) -> bool:
        """Check if there's a next challenge to complete."""
        return self.current_challenge_index < len(self.challenges) - 1

    def move_to_next_challenge(self) -> bool:
        """Move to the next challenge. Returns True if successful."""
        if self.has_next_challenge():
            self.current_challenge_index += 1
            return True
        return False

    def all_challenges_completed(self) -> bool:
        """Check if all challenges are completed."""
        return all(c.completed for c in self.challenges)
