import pytest

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Minion, MinionType, Team, TeamColor
from goa2.domain.state import GameState
from goa2.engine.steps import ChooseMinionRemovalStep
from goa2.engine.steps.combat import RemoveUnitStep


@pytest.fixture
def removal_state():
    """A zone holding one heavy and two non-heavy RED minions (the losing team)."""
    board = Board()
    zone_hexes = {Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1), Hex(q=2, r=0, s=-2)}
    board.zones = {"Z": Zone(id="Z", label="Z", hexes=zone_hexes)}
    board.populate_tiles_from_zones()

    heavy = Minion(id="m_heavy", name="Heavy", type=MinionType.HEAVY, team=TeamColor.RED)
    light1 = Minion(id="m_light1", name="Light1", type=MinionType.MELEE, team=TeamColor.RED)
    light2 = Minion(id="m_light2", name="Light2", type=MinionType.MELEE, team=TeamColor.RED)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[heavy, light1, light2]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )
    state.place_entity("m_heavy", Hex(q=0, r=0, s=0))
    state.place_entity("m_light1", Hex(q=1, r=0, s=-1))
    state.place_entity("m_light2", Hex(q=2, r=0, s=-2))
    return state


def _removed_ids(result):
    return [s.unit_id for s in result.new_steps if isinstance(s, RemoveUnitStep)]


def test_removal_rejects_protected_heavy_minion(removal_state):
    """A client cannot remove a heavy minion while non-heavy minions remain."""
    step = ChooseMinionRemovalStep(losing_team="RED", remaining_to_remove=1, zone_id="Z")

    # First resolve: only the two non-heavy minions are offered.
    result = step.resolve(removal_state, {})
    assert result.requires_input
    assert set(result.input_request["candidates"]) == {"m_light1", "m_light2"}

    # Submit the protected heavy minion -> rejected, no removal, re-request.
    step.pending_input = {"selection": "m_heavy"}
    result = step.resolve(removal_state, {})
    assert result.requires_input
    assert _removed_ids(result) == []

    # A valid (non-heavy) choice is still accepted.
    step.pending_input = {"selection": "m_light1"}
    result = step.resolve(removal_state, {})
    assert result.is_finished
    assert _removed_ids(result) == ["m_light1"]
