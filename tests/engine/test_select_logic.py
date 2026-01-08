import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, MinionType
from goa2.engine.steps import SelectStep
from goa2.domain.factory import EntityFactory
from goa2.engine.filters import UnitTypeFilter
from goa2.domain.hex import Hex


@pytest.fixture
def select_state():
    state = GameState(
        board=Board(),
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[])},
        current_actor_id="hero_red",
    )
    m1 = EntityFactory.create_minion(state, TeamColor.RED, MinionType.MELEE)
    state.register_entity(m1, "minion")

    h = Hex(q=0, r=0, s=0)
    state.board.tiles[h] = state.board.get_tile(h)
    state.place_entity(m1.id, h)

    actor_hex = Hex(q=2, r=0, s=-2)
    state.board.tiles[actor_hex] = state.board.get_tile(actor_hex)
    state.place_entity("hero_red", actor_hex)

    return state, m1


def test_optional_select_disables_autoselect(select_state):
    """
    Rule Check: If a step is optional ("You may..."), it should NOT auto-select
    even if only one candidate exists, because the player might want to skip.
    """
    state, minion = select_state

    step = SelectStep(
        target_type="UNIT",
        prompt="Select target (Optional)",
        is_mandatory=False,
        auto_select_if_one=True,
        filters=[UnitTypeFilter(unit_type="MINION")],
    )

    context = {}
    result = step.resolve(state, context)

    assert result.requires_input is True
    assert result.input_request["can_skip"] is True
    assert "selection" not in context


def test_mandatory_select_enables_autoselect(select_state):
    """
    Rule Check: If a step is mandatory and there's only one choice,
    the engine SHOULD auto-select to save time.
    """
    state, minion = select_state

    step = SelectStep(
        target_type="UNIT",
        prompt="Select target (Mandatory)",
        is_mandatory=True,
        auto_select_if_one=True,
        filters=[UnitTypeFilter(unit_type="MINION")],
    )

    context = {}
    result = step.resolve(state, context)

    assert result.is_finished is True
    assert context["selection"] == minion.id


def test_optional_select_skip_input(select_state):
    """
    Rule Check: Providing "SKIP" to an optional step works.
    """
    state, minion = select_state

    step = SelectStep(
        target_type="UNIT",
        prompt="Select target (Optional)",
        is_mandatory=False,
        filters=[UnitTypeFilter(unit_type="MINION")],
    )

    context = {}

    step.pending_input = {"selection": "SKIP"}

    result = step.resolve(state, context)

    assert result.is_finished is True
    assert "selection" not in context
