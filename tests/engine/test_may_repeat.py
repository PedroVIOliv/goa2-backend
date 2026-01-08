import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Modifier, DurationType
from goa2.domain.types import BoardEntityID, ModifierID
from goa2.engine.steps import MayRepeatOnceStep, LogMessageStep, StepResult


@pytest.fixture
def empty_state():
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_1",
    )


def test_may_repeat_flow(empty_state: GameState):
    state = empty_state

    # 1. Setup the step with a simple log template
    template = [LogMessageStep(message="Repeated Action!")]
    step = MayRepeatOnceStep(steps_template=template)

    # 2. Initial execution -> Should prompt
    res = step.resolve(state, state.execution_context)
    assert res.requires_input is True
    assert res.input_request["type"] == "SELECT_OPTION"

    # 3. Provide "YES" -> Should spawn steps
    step.pending_input = {"selection": "YES"}
    res = step.resolve(state, state.execution_context)
    assert res.is_finished is True
    assert len(res.new_steps) == 1
    assert isinstance(res.new_steps[0], LogMessageStep)

    # 4. Provide "NO" -> Should finish without steps
    step.pending_input = {"selection": "NO"}
    res = step.resolve(state, state.execution_context)
    assert res.is_finished is True
    assert len(res.new_steps) == 0


def test_may_repeat_prevention(empty_state: GameState):
    state = empty_state
    actor_id = "hero_1"

    # Add PREVENT_ACTION_REPEAT
    mod = Modifier(
        id=ModifierID("mod_prevent"),
        source_id=BoardEntityID("source"),
        target_id=BoardEntityID(actor_id),
        status_tag="PREVENT_ACTION_REPEAT",
        duration=DurationType.THIS_TURN,
        created_at_turn=state.turn,
        created_at_round=state.round,
    )
    state.add_modifier(mod)

    step = MayRepeatOnceStep(steps_template=[LogMessageStep(message="Blocked")])

    # Execution -> Should finish immediately (blocked)
    res = step.resolve(state, state.execution_context)
    assert res.is_finished is True
    assert len(res.new_steps) == 0
    # Ideally check stdout for "Blocked by validation" but implicit check via new_steps=0 is fine
