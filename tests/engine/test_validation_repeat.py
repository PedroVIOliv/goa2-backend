import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Modifier, DurationType
from goa2.domain.types import BoardEntityID, ModifierID
from goa2.engine.effect_manager import EffectManager


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


def test_prevent_action_repeat(empty_state: GameState):
    state = empty_state
    actor_id = "hero_1"

    # 1. No modifier -> Allowed
    res = state.validator.can_repeat_action(state, actor_id)
    assert res.allowed is True

    # 2. Add PREVENT_ACTION_REPEAT modifier
    mod = Modifier(
        id=ModifierID("mod_1"),
        source_id=BoardEntityID("source_1"),
        target_id=BoardEntityID(actor_id),
        status_tag="PREVENT_ACTION_REPEAT",
        duration=DurationType.THIS_TURN,
        created_at_turn=state.turn,
        created_at_round=state.round,
    )
    state.add_modifier(mod)

    # 3. With modifier -> Denied
    res = state.validator.can_repeat_action(state, actor_id)
    assert res.allowed is False
    assert "Action repeat prevented" in res.reason
    assert "mod_1" in res.blocking_modifier_ids
