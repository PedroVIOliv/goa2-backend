import pytest
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
    CardState,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import (
    ForceDiscardStep,
)
from goa2.engine.filters import LineBehindTargetFilter
from goa2.engine.handler import process_resolution_stack, push_steps


@pytest.fixture
def mechanics_state():
    """
    Board setup for geometric tests:
    - (0,0,0): Origin (A)
    - (1,0,-1): Target (B) - Directly East
    - (2,0,-2): Behind 1 (C)
    - (3,0,-3): Behind 2 (D)
    - (1,-1,0): Flanker (E) - Not behind
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=3, r=0, s=-3),
        Hex(q=1, r=-1, s=0),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero_a = Hero(id="A", name="A", team=TeamColor.RED, deck=[], level=1)
    hero_b = Hero(id="B", name="B", team=TeamColor.BLUE, deck=[], level=1)
    hero_c = Hero(id="C", name="C", team=TeamColor.BLUE, deck=[], level=1)
    hero_d = Hero(id="D", name="D", team=TeamColor.BLUE, deck=[], level=1)
    hero_e = Hero(id="E", name="E", team=TeamColor.BLUE, deck=[], level=1)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_a], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=[hero_b, hero_c, hero_d, hero_e],
                minions=[],
            ),
        },
    )

    state.place_entity("A", Hex(q=0, r=0, s=0))
    state.place_entity("B", Hex(q=1, r=0, s=-1))
    state.place_entity("C", Hex(q=2, r=0, s=-2))
    state.place_entity("D", Hex(q=3, r=0, s=-3))
    state.place_entity("E", Hex(q=1, r=-1, s=0))

    state.current_actor_id = "A"
    return state


def test_line_behind_target_filter(mechanics_state):
    """
    Verify geometry of LineBehindTargetFilter.
    Origin: A (0,0,0)
    Target: B (1,0,-1)
    Expected Line: C (2,0,-2) and D (3,0,-3)
    Excluded: E (1,-1,0) - Adjacent but not behind
    """

    # 1. Test Length 1 (Should capture C only)
    filter_1 = LineBehindTargetFilter(target_key="target_id", length=1)
    context = {"target_id": "B"}

    # Candidates: C, D, E
    assert filter_1.apply("C", mechanics_state, context) is True
    assert filter_1.apply("D", mechanics_state, context) is False  # Too far
    assert filter_1.apply("E", mechanics_state, context) is False  # Wrong direction

    # 2. Test Length 2 (Should capture C and D)
    filter_2 = LineBehindTargetFilter(target_key="target_id", length=2)

    assert filter_2.apply("C", mechanics_state, context) is True
    assert filter_2.apply("D", mechanics_state, context) is True
    assert filter_2.apply("E", mechanics_state, context) is False


def test_force_discard_safe_empty_hand(mechanics_state):
    """
    Test ForceDiscardStep (Safe Version) when victim has NO cards.
    Should simply finish without error or defeat.
    """
    victim = mechanics_state.get_hero("C")
    victim.hand = []  # Empty hand

    step = ForceDiscardStep(victim_key="victim_id")
    mechanics_state.execution_context["victim_id"] = "C"

    push_steps(mechanics_state, [step])

    # Execute
    process_resolution_stack(mechanics_state)

    # Verify State: Victim still exists, no new steps spawned (like Defeat)
    assert "C" in mechanics_state.entity_locations
    # If it spawned Defeat, C would be removed or DefeatStep would be in stack
    assert len(mechanics_state.execution_stack) == 0


def test_force_discard_safe_with_hand(mechanics_state):
    """
    Test ForceDiscardStep (Safe Version) when victim HAS cards.
    Should prompt for discard.
    """
    victim = mechanics_state.get_hero("C")
    card = Card(
        id="c1",
        name="Card",
        tier=CardTier.I,
        color=CardColor.RED,
        primary_action=ActionType.ATTACK,
        state=CardState.HAND,
        initiative=5,
        primary_action_value=1,
        effect_id="",
        effect_text="",
    )
    victim.hand = [card]

    step = ForceDiscardStep(victim_key="victim_id")
    mechanics_state.execution_context["victim_id"] = "C"

    push_steps(mechanics_state, [step])

    # Execute -> Should request input
    req = process_resolution_stack(mechanics_state)

    assert req["type"] == "SELECT_CARD"
    assert req["player_id"] == "C"

    # Provide input
    mechanics_state.execution_stack[-1].pending_input = {"selection": "c1"}
    process_resolution_stack(mechanics_state)

    # Verify Discard
    assert len(victim.hand) == 0
    assert len(victim.discard_pile) == 1
    assert victim.discard_pile[0].id == "c1"
