"""Phase 8 policy precedence tests for similarity + liveness + risk."""

from sentinelid_edge.domain.models import AuthSession, Challenge, ChallengeType
from sentinelid_edge.domain.policy import PolicyEngine
from sentinelid_edge.domain.reasons import ReasonCode


def _completed_session(liveness_passed: bool = True) -> AuthSession:
    challenge = Challenge(ChallengeType.BLINK)
    challenge.completed = True
    challenge.passed = liveness_passed
    return AuthSession(
        session_id="s",
        challenges=[challenge],
        liveness_passed=liveness_passed,
    )


def test_policy_denies_when_not_enrolled() -> None:
    engine = PolicyEngine(similarity_threshold=0.6, risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_session(liveness_passed=True)

    decision = engine.evaluate(
        session,
        template_enrolled=False,
        similarity_score=0.99,
        enforce_similarity=True,
        risk_score=0.1,
    )
    assert decision.decision == "deny"
    assert ReasonCode.NOT_ENROLLED in decision.reason_codes


def test_policy_liveness_failure_precedes_similarity_and_risk() -> None:
    engine = PolicyEngine(similarity_threshold=0.6, risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_session(liveness_passed=False)

    decision = engine.evaluate(
        session,
        template_enrolled=True,
        similarity_score=0.95,
        enforce_similarity=True,
        risk_score=0.95,
    )
    assert decision.decision == "deny"
    assert decision.reason_codes == [ReasonCode.LIVENESS_FAILED]


def test_policy_similarity_below_threshold_denies() -> None:
    engine = PolicyEngine(similarity_threshold=0.6, risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_session(liveness_passed=True)

    decision = engine.evaluate(
        session,
        template_enrolled=True,
        similarity_score=0.59,
        enforce_similarity=True,
        risk_score=0.1,
    )
    assert decision.decision == "deny"
    assert ReasonCode.SIMILARITY_BELOW_THRESHOLD in decision.reason_codes


def test_policy_high_risk_denies_after_similarity_pass() -> None:
    engine = PolicyEngine(similarity_threshold=0.6, risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_session(liveness_passed=True)

    decision = engine.evaluate(
        session,
        template_enrolled=True,
        similarity_score=0.9,
        enforce_similarity=True,
        risk_score=0.8,
    )
    assert decision.decision == "deny"
    assert ReasonCode.RISK_HIGH in decision.reason_codes


def test_policy_medium_risk_triggers_step_up() -> None:
    engine = PolicyEngine(similarity_threshold=0.6, risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_session(liveness_passed=True)

    decision = engine.evaluate(
        session,
        template_enrolled=True,
        similarity_score=0.9,
        enforce_similarity=True,
        risk_score=0.5,
    )
    assert decision.decision == "step_up"
    assert ReasonCode.RISK_STEP_UP in decision.reason_codes


def test_policy_low_risk_allows_after_all_gates_pass() -> None:
    engine = PolicyEngine(similarity_threshold=0.6, risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_session(liveness_passed=True)

    decision = engine.evaluate(
        session,
        template_enrolled=True,
        similarity_score=0.9,
        enforce_similarity=True,
        risk_score=0.2,
    )
    assert decision.decision == "allow"
    assert decision.similarity_score == 0.9
