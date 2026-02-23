"""Phase 7 policy threshold tests (ALLOW/STEP_UP/DENY)."""

from sentinelid_edge.domain.models import AuthSession, Challenge, ChallengeType
from sentinelid_edge.domain.policy import PolicyEngine
from sentinelid_edge.domain.reasons import ReasonCode


def _completed_primary_session() -> AuthSession:
    challenge = Challenge(ChallengeType.BLINK)
    challenge.completed = True
    challenge.passed = True
    return AuthSession(
        session_id="session-primary",
        challenges=[challenge],
        liveness_passed=True,
    )


def _completed_step_up_session() -> AuthSession:
    primary = Challenge(ChallengeType.BLINK)
    primary.completed = True
    primary.passed = True

    step_up = Challenge(ChallengeType.TURN_LEFT)
    step_up.completed = True
    step_up.passed = True

    session = AuthSession(
        session_id="session-step-up",
        challenges=[primary],
        liveness_passed=True,
    )
    session.start_step_up([step_up])
    return session


def test_policy_risk_below_r1_allows() -> None:
    engine = PolicyEngine(risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_primary_session()

    decision = engine.evaluate(session, risk_score=0.39, risk_reasons=[])
    assert decision.decision == "allow"
    assert decision.reason_codes == [ReasonCode.LIVENESS_PASSED]


def test_policy_risk_equal_r1_steps_up() -> None:
    engine = PolicyEngine(risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_primary_session()

    decision = engine.evaluate(
        session,
        risk_score=0.4,
        risk_reasons=[ReasonCode.SPOOF_SUSPECT_SCREEN],
    )
    assert decision.decision == "step_up"
    assert ReasonCode.RISK_STEP_UP in decision.reason_codes


def test_policy_risk_between_thresholds_steps_up() -> None:
    engine = PolicyEngine(risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_primary_session()

    decision = engine.evaluate(session, risk_score=0.55, risk_reasons=[])
    assert decision.decision == "step_up"


def test_policy_risk_equal_r2_denies() -> None:
    engine = PolicyEngine(risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_primary_session()

    decision = engine.evaluate(session, risk_score=0.7, risk_reasons=[])
    assert decision.decision == "deny"
    assert ReasonCode.RISK_HIGH in decision.reason_codes


def test_policy_force_final_allows_after_step_up() -> None:
    engine = PolicyEngine(risk_threshold_r1=0.4, risk_threshold_r2=0.7)
    session = _completed_step_up_session()

    decision = engine.evaluate(session, risk_score=0.5, risk_reasons=[], force_final=True)
    assert decision.decision == "allow"


def test_policy_mid_risk_denied_when_max_stepups_reached() -> None:
    engine = PolicyEngine(risk_threshold_r1=0.4, risk_threshold_r2=0.7, max_step_ups=1)
    session = _completed_primary_session()
    session.step_up_count = 1

    decision = engine.evaluate(session, risk_score=0.5, risk_reasons=[])
    assert decision.decision == "deny"
    assert ReasonCode.MAX_STEP_UPS_REACHED in decision.reason_codes
