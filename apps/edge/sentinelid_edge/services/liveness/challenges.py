"""
Session management and challenge generation for liveness verification.
"""
import uuid
import random
import time
from typing import Optional, List, Dict
from ...domain.models import AuthSession, Challenge, ChallengeType
from ...domain.reasons import ReasonCode


class SessionStore:
    """In-memory session store with TTL cleanup."""

    def __init__(self, session_timeout_seconds: int = 120):
        self.sessions: Dict[str, AuthSession] = {}
        self.session_timeout_seconds = session_timeout_seconds

    def create_session(self, challenges: List[Challenge]) -> AuthSession:
        """Create a new authentication session with given challenges."""
        session_id = str(uuid.uuid4())
        session = AuthSession(
            session_id=session_id,
            challenges=challenges,
            session_timeout_seconds=self.session_timeout_seconds,
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[AuthSession]:
        """Retrieve a session by ID, or None if not found."""
        session = self.sessions.get(session_id)
        if session and session.is_expired():
            # Clean up expired session
            del self.sessions[session_id]
            return None
        return session

    def save_session(self, session: AuthSession) -> None:
        """Update a session in the store."""
        self.sessions[session.session_id] = session

    def delete_session(self, session_id: str) -> None:
        """Delete a session from the store."""
        if session_id in self.sessions:
            del self.sessions[session_id]

    def cleanup_expired(self) -> None:
        """Remove all expired sessions."""
        expired_ids = [
            sid for sid, session in self.sessions.items()
            if session.is_expired()
        ]
        for sid in expired_ids:
            del self.sessions[sid]


class ChallengeGenerator:
    """Generates randomized liveness challenges."""

    # All possible challenge types
    AVAILABLE_CHALLENGES = [
        ChallengeType.BLINK,
        ChallengeType.TURN_LEFT,
        ChallengeType.TURN_RIGHT,
    ]

    # Minimum and maximum challenges per session
    MIN_CHALLENGES = 2
    MAX_CHALLENGES = 3

    def __init__(self, challenge_timeout_seconds: int = 10):
        self.challenge_timeout_seconds = challenge_timeout_seconds

    def generate_challenges(self) -> List[Challenge]:
        """
        Generate a randomized list of liveness challenges.

        Returns:
            A list of 2-3 challenges in random order.
        """
        # Randomly select number of challenges
        num_challenges = random.randint(self.MIN_CHALLENGES, self.MAX_CHALLENGES)

        # Randomly select and shuffle challenges
        selected = random.sample(self.AVAILABLE_CHALLENGES, num_challenges)
        random.shuffle(selected)

        # Create Challenge objects
        challenges = [
            Challenge(
                challenge_type=challenge_type,
                timeout_seconds=self.challenge_timeout_seconds,
            )
            for challenge_type in selected
        ]

        return challenges

    @staticmethod
    def get_challenge_instructions(challenge_type: ChallengeType) -> str:
        """Return human-readable instructions for a challenge type."""
        instructions = {
            ChallengeType.BLINK: "Please blink your eyes. Wait for the prompt and blink naturally.",
            ChallengeType.TURN_LEFT: "Please turn your head slowly to the left.",
            ChallengeType.TURN_RIGHT: "Please turn your head slowly to the right.",
        }
        return instructions.get(challenge_type, "Please complete this challenge.")
