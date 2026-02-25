import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor
from goa2.engine.steps import (
    AskConfirmationStep,
    RecordTargetStep,
)
from goa2.engine.filters import ExcludeIdentityFilter


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


def test_repeat_logic_infrastructure(empty_state: GameState):
    state = empty_state

    # 1. Test RecordTargetStep
    state.execution_context["target_1"] = "minion_1"

    step = RecordTargetStep(input_key="target_1", output_list_key="history")
    step.resolve(state, state.execution_context)

    assert "history" in state.execution_context
    assert state.execution_context["history"] == ["minion_1"]

    # 2. Test ExcludeIdentityFilter with List
    filter_obj = ExcludeIdentityFilter(exclude_keys=["history"])

    # "minion_1" should be excluded
    assert filter_obj.apply("minion_1", state, state.execution_context) is False
    # "minion_2" should be allowed
    assert filter_obj.apply("minion_2", state, state.execution_context) is True

    # 3. Test AskConfirmationStep
    ask = AskConfirmationStep(prompt="Repeat?", output_key="do_repeat")

    # Initial call -> Request Input
    res = ask.resolve(state, state.execution_context)
    assert res.requires_input is True
    assert res.input_request["type"] == "SELECT_OPTION"

    # Provide Input -> YES
    ask.pending_input = {"selection": "YES"}
    res = ask.resolve(state, state.execution_context)
    assert res.is_finished is True
    assert state.execution_context["do_repeat"] is True

    # Provide Input -> NO
    ask.pending_input = {"selection": "NO"}
    res = ask.resolve(state, state.execution_context)
    assert state.execution_context["do_repeat"] is False
