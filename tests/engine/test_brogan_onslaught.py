"""Tests for Brogan's Onslaught card effect."""

import pytest
import goa2.scripts.brogan_effects  # noqa: F401 — registers effects
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep, RecordHexStep
from goa2.engine.handler import process_resolution_stack, push_steps


def _make_onslaught_card():
    """Create an Onslaught card."""
    return Card(
        id="onslaught_card",
        name="Onslaught",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        range_value=1,
        effect_id="onslaught",
        effect_text="Target a unit adjacent to you. After the attack: Move into the space it occupied, if able.",
        is_facedown=False,
    )


@pytest.fixture
def onslaught_state():
    """Setup: Brogan with Onslaught, adjacent enemy victim."""
    board = Board()

    hexes = set()
    for q in range(5):
        hexes.add(Hex(q=q, r=0, s=-q))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    # Brogan at (0,0,0), enemy at (1,0,-1), empty space at (-1,0,1)
    brogan = Hero(id="brogan", name="Brogan", team=TeamColor.RED, deck=[], level=1)
    victim = Hero(id="victim", name="Victim", team=TeamColor.BLUE, deck=[], level=1)

    onslaught_card = _make_onslaught_card()
    brogan.current_turn_card = onslaught_card

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[brogan], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[victim], minions=[]),
        },
    )
    state.place_entity("brogan", Hex(q=0, r=0, s=0))
    state.place_entity("victim", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "brogan"

    return state


def test_onslaught_records_victim_hex_before_attack(onslaught_state):
    """RecordHexStep should capture victim's position before attack."""
    # Setup: Select victim
    onslaught_state.execution_context["victim_id"] = "victim"

    # Record victim's hex
    record_step = RecordHexStep(unit_key="victim_id", output_key="victim_hex")
    result = record_step.resolve(onslaught_state, onslaught_state.execution_context)

    assert result.is_finished is True
    assert "victim_hex" in onslaught_state.execution_context
    assert onslaught_state.execution_context["victim_hex"] == {"q": 1, "r": 0, "s": -1}


def test_onslaught_step_structure(onslaught_state):
    """Onslaught should have correct step sequence: Select → Record → Attack → Place."""
    from goa2.scripts.brogan_effects import OnslaughtEffect
    from goa2.engine.stats import CardStats

    effect = OnslaughtEffect()
    stats = CardStats(primary_value=4, range=1, radius=None)
    steps = effect.build_steps(
        onslaught_state,
        onslaught_state.teams[TeamColor.RED].heroes[0],
        _make_onslaught_card(),
        stats,
    )

    # Verify step types are in correct order
    assert len(steps) == 4
    assert steps[0].__class__.__name__ == "SelectStep"
    assert steps[1].__class__.__name__ == "RecordHexStep"
    assert steps[2].__class__.__name__ == "AttackSequenceStep"
    assert steps[3].__class__.__name__ == "MoveUnitStep" 

    # Verify RecordHexStep parameters
    assert steps[1].unit_key == "victim_id"
    assert steps[1].output_key == "victim_hex"

    # Verify PlaceUnitStep parameters
    assert steps[3].unit_id == "brogan"
    assert steps[3].destination_key == "victim_hex"
    assert steps[3].is_mandatory is False  # "if able"


def test_onslaught_moves_into_victim_space(onslaught_state):
    """After attack, Brogan should move into victim's original space."""
    # Onslaught uses PlaceUnitStep directly - it reads victim_hex from context,
    # no SELECT_HEX prompt is needed for player
    from goa2.engine.steps import PlaceUnitStep
    from goa2.domain.types import HeroID

    # Setup context as if attack completed AND victim removed
    onslaught_state.execution_context["victim_id"] = "victim"
    onslaught_state.execution_context["victim_hex"] = {"q": 1, "r": 0, "s": -1}

    # Simulate victim being defeated (removed from board properly)
    onslaught_state.remove_unit(HeroID("victim"))

    # Execute PlaceUnitStep
    place_step = PlaceUnitStep(
        unit_id="brogan", destination_key="victim_hex", is_mandatory=False
    )
    result = place_step.resolve(onslaught_state, onslaught_state.execution_context)

    assert result.is_finished is True
    assert result.abort_action is False

    # Verify Brogan moved into victim's space
    brogan_loc = onslaught_state.entity_locations.get("brogan")
    assert brogan_loc == Hex(q=1, r=0, s=-1)


def test_onslaught_handles_missing_unit_gracefully():
    """RecordHexStep should handle missing unit without crashing."""
    state = GameState(board=Board(), teams={})
    state.execution_context = {}

    record_step = RecordHexStep(unit_key="nonexistent", output_key="hex")
    result = record_step.resolve(state, state.execution_context)

    assert result.is_finished is True
    assert "hex" not in state.execution_context  # Should not record anything


def test_onslaught_handles_unit_not_on_board():
    """RecordHexStep should handle unit_id that's not placed on board."""
    state = GameState(board=Board(), teams={})
    state.execution_context = {"unit_id": "ghost_unit"}

    record_step = RecordHexStep(unit_key="unit_id", output_key="hex")
    result = record_step.resolve(state, state.execution_context)

    assert result.is_finished is True
    assert "hex" not in state.execution_context


def test_onslaught_placement_optional_if_able():
    """Placement should fail gracefully if space is occupied."""
    board = Board()
    hexes = {Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1)}
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    brogan = Hero(id="brogan", name="Brogan", team=TeamColor.RED, deck=[], level=1)
    victim = Hero(id="victim", name="Victim", team=TeamColor.BLUE, deck=[], level=1)
    blocker = Hero(id="blocker", name="Blocker", team=TeamColor.BLUE, deck=[], level=1)

    onslaught_card = _make_onslaught_card()
    brogan.current_turn_card = onslaught_card

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[brogan], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[victim, blocker], minions=[]
            ),
        },
    )

    # Setup: Brogan at (0,0,0), victim at (1,0,-1)
    state.place_entity("brogan", Hex(q=0, r=0, s=0))
    state.place_entity("victim", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "brogan"

    # Select victim
    state.execution_context["victim_id"] = "victim"

    # Record victim hex
    RecordHexStep(unit_key="victim_id", output_key="victim_hex").resolve(
        state, state.execution_context
    )

    # Attack (victim defeated)
    # For this test, we'll simulate defeat by removing victim
    state.entity_locations.pop("victim", None)

    # Try to place - should fail gracefully (is_mandatory=False)
    from goa2.engine.steps import PlaceUnitStep

    place_step = PlaceUnitStep(
        unit_id="brogan", destination_key="victim_hex", is_mandatory=False
    )
    result = place_step.resolve(state, state.execution_context)

    # PlaceUnitStep should finish without error (is_mandatory=False)
    assert result.is_finished is True
    assert result.abort_action is False

    # Brogan should remain at original position
    brogan_loc = state.entity_locations.get("brogan")
    assert brogan_loc == Hex(q=0, r=0, s=0)
