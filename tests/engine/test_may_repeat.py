import pytest

from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor
from goa2.domain.state import GameState
from goa2.engine.steps import LogMessageStep, MayRepeatNTimesStep, MayRepeatOnceStep


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


def test_may_repeat_n_times_prompts_between_yes_answers(empty_state: GameState):
    state = empty_state

    step = MayRepeatNTimesStep(
        max_repeats=2,
        steps_template=[LogMessageStep(message="Repeated Action!")],
    )

    res = step.resolve(state, state.execution_context)
    assert res.requires_input is True
    assert res.input_request["type"] == "SELECT_OPTION"

    step.pending_input = {"selection": "YES"}
    res = step.resolve(state, state.execution_context)
    assert res.is_finished is False
    assert step.repeats_done == 1
    assert step.pending_input is None
    assert len(res.new_steps) == 1

    res = step.resolve(state, state.execution_context)
    assert res.requires_input is True
    assert res.input_request["type"] == "SELECT_OPTION"
    assert "1/2 done" in res.input_request.prompt
