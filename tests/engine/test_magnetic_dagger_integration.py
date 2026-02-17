import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    Card,
    CardTier,
    CardColor,
    ActionType,
    GamePhase,
)
from goa2.domain.hex import Hex
from goa2.domain.tile import Tile
from goa2.engine.handler import process_resolution_stack
from goa2.engine.phases import commit_card
import goa2.scripts.arien_effects  # Register Arien effects
import goa2.scripts.rogue_effects  # Register Rogue effects
import goa2.scripts.wasp_effects  # Register Wasp effects


@pytest.fixture
def integrated_state():
    board = Board()
    for q in range(-6, 7):
        for r in range(-6, 7):
            if abs(q + r) <= 6:
                h = Hex(q=q, r=r, s=-(q + r))
                board.tiles[h] = Tile(hex=h)

    rogue = Hero(id="rogue", name="Rogue", team=TeamColor.RED, deck=[], level=1)
    arien = Hero(id="arien", name="Arien", team=TeamColor.BLUE, deck=[], level=1)

    dummy = Minion(id="dummy", name="Dummy", type=MinionType.MELEE, team=TeamColor.BLUE)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[rogue], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[arien], minions=[dummy]),
        },
        turn=1,
        round=1,
        phase=GamePhase.PLANNING,
        tie_breaker_team=TeamColor.RED,  # Ensure Rogue wins initiative ties
    )
    return state


def setup_game(state, rogue_card_id="magnetic_dagger", arien_card_id="liquid_leap"):
    rogue = state.get_hero("rogue")
    arien = state.get_hero("arien")

    # Create Rogue Card
    if rogue_card_id == "magnetic_dagger":
        c = Card(
            id="magnetic_dagger",
            name="Magnetic Dagger",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=12,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            radius_value=3,
            effect_id="magnetic_dagger",
            effect_text="Target a unit adjacent to you. After the attack: This turn: Enemy units in radius cannot be swapped or placed by themselves or by enemy heroes.",
            is_facedown=True,
        )
        rogue.hand = [c]

    # Create Arien Card
    if arien_card_id == "liquid_leap":
        c = Card(
            id="liquid_leap",
            name="Liquid Leap",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            range_value=3,
            effect_id="liquid_leap",
            effect_text="Place yourself...",
            is_facedown=True,
        )
        arien.hand = [c]


def run_full_turn(state, rogue_target="dummy", arien_target_hex=None):
    """
    Simulates the full turn loop:
    1. Players commit cards.
    2. Engine resolves Phase 1 (Rogue).
    3. Engine resolves Phase 2 (Arien).
    """
    rogue = state.get_hero("rogue")
    arien = state.get_hero("arien")

    # 1. PLANNING PHASE
    commit_card(state, "rogue", rogue.hand[0])
    commit_card(state, "arien", arien.hand[0])

    # State should now be in RESOLUTION, stack populated with Rogue (Winner of tie)
    # Rogue Turn Flow:
    # 1. CHOOSE_ACTION -> ATTACK
    # 2. SELECT_UNIT (Target) -> rogue_target
    # 3. SELECT_CARD_OR_PASS (Reaction) -> PASS

    # -- Rogue's Turn --
    req = process_resolution_stack(state)
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "rogue"
    state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_UNIT"  # Attack Target
    state.execution_stack[-1].pending_input = {"selection": rogue_target}

    req = process_resolution_stack(state)
    if req and req["type"] == "SELECT_CARD_OR_PASS":  # Reaction
        state.execution_stack[-1].pending_input = {"selected_card_id": "PASS"}
        req = process_resolution_stack(state)

    # Rogue turn finishes. Effect created.
    # Engine automatically loops to FindNextActor -> Arien.

    # -- Arien's Turn --
    # 1. CHOOSE_ACTION -> SKILL
    # 2. SELECT_HEX (Target) -> arien_target_hex

    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "arien"
    state.execution_stack[-1].pending_input = {"selection": "SKILL"}

    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_HEX"
    if arien_target_hex:
        state.execution_stack[-1].pending_input = {"selection": arien_target_hex}

    # Execute Placement (will fail if blocked)
    process_resolution_stack(state)


def test_integration_dagger_blocks_leap(integrated_state):
    state = integrated_state

    # Setup Positions: Rogue(0,0,0), Arien(2,0,-2) [Dist 2], Dummy(1,0,-1)
    state.place_entity("rogue", Hex(q=0, r=0, s=0))
    state.place_entity("arien", Hex(q=2, r=0, s=-2))
    state.place_entity("dummy", Hex(q=1, r=0, s=-1))

    setup_game(state)

    # Run the turn
    # Arien tries to jump to (3,0,-3)
    target_hex = Hex(q=3, r=0, s=-3)
    run_full_turn(state, rogue_target="dummy", arien_target_hex=target_hex)

    # Verify: Arien NOT moved (Blocked)
    assert state.entity_locations["arien"] == Hex(q=2, r=0, s=-2)


def test_integration_edge_case_boundary(integrated_state):
    """
    Edge Case: Arien EXACTLY at Radius 3 tries to leap OUT to Dist 4.
    Should be BLOCKED because he starts in the prevention zone.
    """
    state = integrated_state

    # Setup: Rogue(0,0,0), Arien(3,0,-3) [Dist 3], Dummy(1,0,-1)
    state.place_entity("rogue", Hex(q=0, r=0, s=0))
    state.place_entity("arien", Hex(q=3, r=0, s=-3))
    state.place_entity("dummy", Hex(q=1, r=0, s=-1))

    setup_game(state)

    # 1. Rogue Uses Dagger on Dummy
    # 2. Arien Uses Leap to (4,0,-4) (OUTSIDE Radius 3)
    target = Hex(q=4, r=0, s=-4)
    run_full_turn(state, rogue_target="dummy", arien_target_hex=target)

    # Verify Blocked (Arien still at start)
    assert state.entity_locations["arien"] == Hex(q=3, r=0, s=-3)


def test_integration_outside_range_allowed(integrated_state):
    state = integrated_state

    # Setup: Rogue(0,0,0), Arien(4,0,-4) [Dist 4], Dummy(1,0,-1)
    state.place_entity("rogue", Hex(q=0, r=0, s=0))
    state.place_entity("arien", Hex(q=4, r=0, s=-4))
    state.place_entity("dummy", Hex(q=1, r=0, s=-1))

    setup_game(state)

    # Arien jumps to (5,0,-5)
    target_hex = Hex(q=5, r=0, s=-5)
    run_full_turn(state, rogue_target="dummy", arien_target_hex=target_hex)

    # Verify: Moved (Allowed)
    assert state.entity_locations["arien"] == target_hex
