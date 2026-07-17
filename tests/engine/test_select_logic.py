import pytest

from goa2.domain.board import Board
from goa2.domain.factory import EntityFactory
from goa2.domain.hex import Hex
from goa2.domain.models import MinionType, Team, TeamColor
from goa2.domain.state import GameState
from goa2.engine.filters import UnitTypeFilter
from goa2.engine.steps import SelectStep


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
    state, _minion = select_state

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
    state, _minion = select_state

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


def test_optional_select_null_does_not_skip(select_state):
    """
    Contract guard (QW1): submitting `null` must NOT skip an optional step.

    The client skip sentinel is the literal string "SKIP". A `null` selection
    is an invalid choice, so the step re-requests input rather than skipping.
    This pins the behavior the CLIENT_INTEGRATION_GUIDE documents.
    """
    state, _minion = select_state

    step = SelectStep(
        target_type="UNIT",
        prompt="Select target (Optional)",
        is_mandatory=False,
        filters=[UnitTypeFilter(unit_type="MINION")],
    )

    context = {}

    step.pending_input = {"selection": None}

    result = step.resolve(state, context)

    # Re-requests input (does not skip, does not record a selection).
    assert result.requires_input is True
    assert result.input_request is not None
    assert "selection" not in context


def test_skip_sentinel_constants_match_contract():
    """The SKIP/DONE sentinels are exactly the strings the client submits."""
    from goa2.domain.input import DONE, SKIP

    assert SKIP == "SKIP"
    assert DONE == "DONE"


def test_number_select_non_numeric_input_rerequests(select_state):
    """A non-numeric selection for a NUMBER step must NOT crash the engine.

    The type coercion (`int(selection)`) previously ran before the
    valid-candidate check, so a bogus client value raised ValueError and the
    already-popped step was lost, corrupting the stack. It must re-request.
    """
    state, _minion = select_state

    step = SelectStep(
        target_type="NUMBER",
        prompt="Pick a number",
        output_key="n",
        number_options=[1, 2, 3],
    )
    step.pending_input = {"selection": "not_a_number"}

    result = step.resolve(state, {})

    assert result.requires_input is True
    assert result.input_request is not None


def test_hex_select_malformed_dict_rerequests(select_state):
    """A malformed hex dict for a HEX step must NOT crash the engine.

    `Hex(**selection)` on a dict missing q/r/s previously raised a pydantic
    ValidationError before the candidate check, losing the popped step. It must
    re-request instead.
    """
    state, _minion = select_state

    step = SelectStep(
        target_type="HEX",
        prompt="Pick a hex",
        output_key="h",
    )
    step.pending_input = {"selection": {"bad": "keys"}}

    result = step.resolve(state, {})

    assert result.requires_input is True
    assert result.input_request is not None
