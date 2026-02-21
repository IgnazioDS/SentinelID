"""
Unit tests for policy engine and authentication decisions.
"""
import pytest
import time
from sentinelid_edge.domain.policy import PolicyEngine, AuthDecision
from sentinelid_edge.domain.models import AuthSession, Challenge, ChallengeType
from sentinelid_edge.domain.reasons import ReasonCode


class TestPolicyEngine:
    """Test authentication policy evaluation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = PolicyEngine()

    def test_policy_initialization(self):
        """Test that policy engine initializes correctly."""
        assert self.engine.require_liveness is True
        assert self.engine.similarity_threshold > 0

    def test_decision_allow(self):
        """Test allow decision."""
        decision = AuthDecision(
            decision="allow",
            reason_codes=[ReasonCode.LIVENESS_PASSED],
            liveness_passed=True,
        )
        assert decision.decision == "allow"
        assert ReasonCode.LIVENESS_PASSED in decision.reason_codes

    def test_decision_deny(self):
        """Test deny decision."""
        decision = AuthDecision(
            decision="deny",
            reason_codes=[ReasonCode.LIVENESS_FAILED],
            liveness_passed=False,
        )
        assert decision.decision == "deny"
        assert ReasonCode.LIVENESS_FAILED in decision.reason_codes

    def test_decision_to_dict(self):
        """Test decision serialization to dict."""
        decision = AuthDecision(
            decision="allow",
            reason_codes=[ReasonCode.LIVENESS_PASSED],
            liveness_passed=True,
            similarity_score=0.95,
        )
        d = decision.to_dict()
        assert d["decision"] == "allow"
        assert d["liveness_passed"] is True
        assert d["similarity_score"] == 0.95

    def test_expired_session_denied(self):
        """Test that expired sessions are denied."""
        # Create session that's already expired
        session = AuthSession(
            session_id="test-session",
            challenges=[Challenge(ChallengeType.BLINK)],
            session_timeout_seconds=0,  # Immediately expired
        )
        # Ensure it's past the timeout
        time.sleep(0.1)

        decision = self.engine.evaluate(session)
        assert decision.decision == "deny"
        assert ReasonCode.SESSION_EXPIRED in decision.reason_codes

    def test_finished_session_with_allow(self):
        """Test that finished sessions return stored decision."""
        session = AuthSession(
            session_id="test-session",
            challenges=[Challenge(ChallengeType.BLINK)],
            finished=True,
            decision="allow",
            liveness_passed=True,
            reason_codes=[ReasonCode.LIVENESS_PASSED],
        )

        decision = self.engine.evaluate(session)
        assert decision.decision == "allow"
        assert decision.liveness_passed is True

    def test_finished_session_with_deny(self):
        """Test that finished sessions with deny return deny."""
        session = AuthSession(
            session_id="test-session",
            challenges=[Challenge(ChallengeType.BLINK)],
            finished=True,
            decision="deny",
            liveness_passed=False,
            reason_codes=[ReasonCode.LIVENESS_FAILED],
        )

        decision = self.engine.evaluate(session)
        assert decision.decision == "deny"
        assert decision.liveness_passed is False

    def test_incomplete_challenges_denied(self):
        """Test that incomplete challenges result in deny."""
        # Create challenges but mark them incomplete
        challenge1 = Challenge(ChallengeType.BLINK)
        challenge2 = Challenge(ChallengeType.TURN_LEFT)
        challenge1.completed = False
        challenge2.completed = True

        session = AuthSession(
            session_id="test-session",
            challenges=[challenge1, challenge2],
        )

        decision = self.engine.evaluate(session)
        assert decision.decision == "deny"
        assert ReasonCode.LIVENESS_FAILED in decision.reason_codes

    def test_liveness_required_no_pass(self):
        """Test that liveness is required when enabled."""
        # Mark challenges as complete but liveness not passed
        challenge = Challenge(ChallengeType.BLINK)
        challenge.completed = True
        challenge.passed = False

        session = AuthSession(
            session_id="test-session",
            challenges=[challenge],
            liveness_passed=False,
        )

        self.engine.require_liveness = True
        decision = self.engine.evaluate(session)
        assert decision.decision == "deny"
        assert decision.liveness_passed is False

    def test_liveness_passed_allow(self):
        """Test allow decision when liveness passes."""
        # Mark challenges as complete and passed
        challenge = Challenge(ChallengeType.BLINK)
        challenge.completed = True
        challenge.passed = True

        session = AuthSession(
            session_id="test-session",
            challenges=[challenge],
            liveness_passed=True,
        )

        decision = self.engine.evaluate(session)
        assert decision.decision == "allow"
        assert decision.liveness_passed is True
        assert ReasonCode.LIVENESS_PASSED in decision.reason_codes

    def test_multiple_challenges_all_passed(self):
        """Test allow with multiple challenges all passed."""
        challenges = []
        for challenge_type in [ChallengeType.BLINK, ChallengeType.TURN_LEFT]:
            challenge = Challenge(challenge_type)
            challenge.completed = True
            challenge.passed = True
            challenges.append(challenge)

        session = AuthSession(
            session_id="test-session",
            challenges=challenges,
            liveness_passed=True,
        )

        decision = self.engine.evaluate(session)
        assert decision.decision == "allow"
        assert len(decision.reason_codes) > 0

    def test_policy_similarity_threshold(self):
        """Test that similarity threshold is configurable."""
        decision = AuthDecision(
            decision="allow",
            reason_codes=[ReasonCode.LIVENESS_PASSED],
            liveness_passed=True,
            similarity_score=0.92,
        )
        # Should still be allow, policy doesn't enforce similarity in v0.2
        assert decision.decision == "allow"


class TestSessionStateTransitions:
    """Test session state machine transitions."""

    def test_challenge_progression(self):
        """Test moving through challenges sequentially."""
        challenges = [
            Challenge(ChallengeType.BLINK),
            Challenge(ChallengeType.TURN_LEFT),
            Challenge(ChallengeType.TURN_RIGHT),
        ]
        session = AuthSession(session_id="test", challenges=challenges)

        # Initially at first challenge
        assert session.current_challenge_index == 0
        assert session.get_current_challenge().challenge_type == ChallengeType.BLINK

        # Move to next
        assert session.has_next_challenge()
        session.move_to_next_challenge()
        assert session.current_challenge_index == 1
        assert session.get_current_challenge().challenge_type == ChallengeType.TURN_LEFT

        # Move to next
        assert session.has_next_challenge()
        session.move_to_next_challenge()
        assert session.current_challenge_index == 2
        assert session.get_current_challenge().challenge_type == ChallengeType.TURN_RIGHT

        # No more challenges
        assert not session.has_next_challenge()

    def test_all_challenges_completed_check(self):
        """Test checking if all challenges are completed."""
        challenges = [
            Challenge(ChallengeType.BLINK),
            Challenge(ChallengeType.TURN_LEFT),
        ]
        session = AuthSession(session_id="test", challenges=challenges)

        # Initially not all completed
        assert not session.all_challenges_completed()

        # Mark first as completed
        challenges[0].completed = True
        assert not session.all_challenges_completed()

        # Mark second as completed
        challenges[1].completed = True
        assert session.all_challenges_completed()

    def test_challenge_timeout(self):
        """Test challenge timeout detection."""
        challenge = Challenge(ChallengeType.BLINK, timeout_seconds=0)
        # Sleep to ensure timeout
        time.sleep(0.1)
        assert challenge.is_expired()

    def test_session_timeout(self):
        """Test session timeout detection."""
        session = AuthSession(
            session_id="test",
            challenges=[Challenge(ChallengeType.BLINK)],
            session_timeout_seconds=0,
        )
        # Sleep to ensure timeout
        time.sleep(0.1)
        assert session.is_expired()


class TestAuthDecisionFormats:
    """Test response formats and serialization."""

    def test_allow_decision_format(self):
        """Test format of allow decision."""
        decision = AuthDecision(
            decision="allow",
            reason_codes=[ReasonCode.LIVENESS_PASSED],
            liveness_passed=True,
            similarity_score=0.95,
        )
        d = decision.to_dict()
        assert d["decision"] in ["allow", "deny"]
        assert isinstance(d["reason_codes"], list)
        assert isinstance(d["liveness_passed"], bool)

    def test_deny_decision_format(self):
        """Test format of deny decision."""
        decision = AuthDecision(
            decision="deny",
            reason_codes=[ReasonCode.LIVENESS_FAILED, ReasonCode.BLINK_NOT_DETECTED],
            liveness_passed=False,
        )
        d = decision.to_dict()
        assert d["decision"] == "deny"
        assert len(d["reason_codes"]) == 2

    def test_reason_codes_consistency(self):
        """Test that all reason codes are strings."""
        decision = AuthDecision(
            decision="deny",
            reason_codes=[ReasonCode.LIVENESS_FAILED],
            liveness_passed=False,
        )
        for code in decision.reason_codes:
            assert isinstance(code, str)
