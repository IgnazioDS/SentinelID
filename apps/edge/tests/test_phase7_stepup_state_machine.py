"""Phase 7 step-up session/state machine tests."""

from sentinelid_edge.domain.models import AuthSession, Challenge, ChallengeType
from sentinelid_edge.services.liveness.evaluator import LivenessEvaluator


def _new_session() -> AuthSession:
    primary = Challenge(ChallengeType.BLINK)
    primary.completed = True
    primary.passed = True
    return AuthSession(session_id="session", challenges=[primary], liveness_passed=True)


def test_start_step_up_sets_expected_flags() -> None:
    session = _new_session()
    step1 = Challenge(ChallengeType.TURN_LEFT)
    step2 = Challenge(ChallengeType.TURN_RIGHT)

    session.start_step_up([step1, step2])

    assert session.in_step_up is True
    assert session.step_up_count == 1
    assert session.step_up_challenge_index == 0
    assert session.get_current_step_up_challenge() == step1


def test_step_up_challenge_progression() -> None:
    session = _new_session()
    step1 = Challenge(ChallengeType.TURN_LEFT)
    step2 = Challenge(ChallengeType.TURN_RIGHT)
    session.start_step_up([step1, step2])

    assert session.has_next_step_up_challenge() is True
    assert session.move_to_next_step_up_challenge() is True
    assert session.step_up_challenge_index == 1
    assert session.has_next_step_up_challenge() is False


def test_clear_step_up_resets_state() -> None:
    session = _new_session()
    session.start_step_up([Challenge(ChallengeType.TURN_LEFT)])

    session.clear_step_up()

    assert session.in_step_up is False
    assert session.step_up_challenges == []
    assert session.step_up_challenge_index == 0


def test_step_up_result_requires_primary_and_step_up_passed() -> None:
    session = _new_session()
    step = Challenge(ChallengeType.TURN_LEFT)
    step.completed = True
    step.passed = True
    session.start_step_up([step])

    evaluator = LivenessEvaluator()
    assert evaluator.evaluate_session_result(session) is True
    assert session.liveness_passed is True


def test_step_up_result_fails_if_any_step_up_challenge_failed() -> None:
    session = _new_session()
    step = Challenge(ChallengeType.TURN_LEFT)
    step.completed = True
    step.passed = False
    session.start_step_up([step])

    evaluator = LivenessEvaluator()
    assert evaluator.evaluate_session_result(session) is False
    assert session.liveness_passed is False
