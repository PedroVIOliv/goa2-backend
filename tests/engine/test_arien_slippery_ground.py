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
    SpawnPoint,
    SpawnType,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps
import goa2.scripts.arien_effects


@pytest.fixture
def slippery_state():
    board = Board()
    # 0,0,0: Arien
    # 1,0,-1: Adjacent Enemy (e1)
    # 2,0,-2: Distant Enemy (e2)
    # 3,0,-3: Empty spawn point (for fast travel)

    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=3, r=0, s=-3),
        Hex(q=4, r=0, s=-4),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])

    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    # Set spawn point on 3,0,-3 for Blue team
    spawn_hex = Hex(q=3, r=0, s=-3)
    board.tiles[spawn_hex].spawn_point = SpawnPoint(
        location=spawn_hex, type=SpawnType.HERO, team=TeamColor.BLUE
    )

    # Arien
    hero = Hero(id="arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="slippery_ground",
        name="Slippery Ground",
        tier=CardTier.II,
        color=CardColor.BLUE,
        initiative=10,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=3,
        effect_id="slippery_ground",
        effect_text="...",
        is_facedown=False,
    )
    hero.current_turn_card = card

    # Enemies
    e1 = Hero(id="e1", name="Adj", team=TeamColor.BLUE, deck=[], level=1)
    e2 = Hero(id="e2", name="Far", team=TeamColor.BLUE, deck=[], level=1)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[e1, e2], minions=[]),
        },
    )

    state.place_entity("arien", Hex(q=0, r=0, s=0))
    state.place_entity("e1", Hex(q=1, r=0, s=-1))
    state.place_entity("e2", Hex(q=2, r=0, s=-2))

    return state


def test_slippery_ground_fast_travel_blocked(slippery_state):
    # 1. Arien activates Slippery Ground
    slippery_state.current_actor_id = "arien"
    step = ResolveCardStep(hero_id="arien")
    push_steps(slippery_state, [step])

    # Action: MOVEMENT (Primary)
    process_resolution_stack(slippery_state)
    slippery_state.execution_stack[-1].pending_input = {"choice_id": "MOVEMENT"}

    # Move selection (Arien stays put)
    process_resolution_stack(slippery_state)
    slippery_state.execution_stack[-1].pending_input = {
        "selection": {"q": 0, "r": 0, "s": 0}
    }

    # Finish turn
    while slippery_state.execution_stack:
        process_resolution_stack(slippery_state)

    # Verify effect created
    assert len(slippery_state.active_effects) == 1

    # 2. Adjacent Enemy (e1) tries to Fast Travel
    res = slippery_state.validator.can_fast_travel(slippery_state, "e1")
    assert res.allowed == False, "Fast Travel should be blocked for adjacent enemy"
    assert "prevented by effect" in res.reason

    # 3. Distant Enemy (e2) tries Fast Travel (should be allowed)
    res = slippery_state.validator.can_fast_travel(slippery_state, "e2")
    assert res.allowed == True, "Fast Travel should be allowed for distant enemy"


def test_slippery_ground_movement_limited(slippery_state):
    # Setup effect (same as above)
    slippery_state.current_actor_id = "arien"
    step = ResolveCardStep(hero_id="arien")
    push_steps(slippery_state, [step])

    process_resolution_stack(slippery_state)
    slippery_state.execution_stack[-1].pending_input = {"choice_id": "MOVEMENT"}

    process_resolution_stack(slippery_state)
    slippery_state.execution_stack[-1].pending_input = {
        "selection": {"q": 0, "r": 0, "s": 0}
    }

    while slippery_state.execution_stack:
        process_resolution_stack(slippery_state)

    # 2. Adjacent Enemy (e1) tries to move 2 spaces via Movement Action
    res = slippery_state.validator.can_move(
        slippery_state, "e1", distance=2, is_movement_action=True
    )
    assert res.allowed == False, "Movement > 1 should be blocked for Movement Action"
    assert "Movement limited to 1" in res.reason

    # 3. Adjacent Enemy (e1) moves via Effect (not action) -> Should be Allowed
    res_effect = slippery_state.validator.can_move(
        slippery_state, "e1", distance=2, is_movement_action=False
    )
    assert res_effect.allowed == True, "Effect movement should NOT be blocked"

    # Try moving 1 space via Action -> Allowed
    res = slippery_state.validator.can_move(
        slippery_state, "e1", distance=1, is_movement_action=True
    )
    assert res.allowed == True
