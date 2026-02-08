import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
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
)
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps
import goa2.scripts.arien_effects


@pytest.fixture
def noble_state():
    board = Board()
    # 0,0,0: Arien
    # 1,0,-1: Enemy 1 (Victim)
    # 0,1,-1: Enemy 2 (Adjacent to Victim)
    # 2,0,-2: Empty (Behind Victim)
    # 1,1,-2: Empty (Adj to Enemy 2)

    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=1, r=1, s=-2),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero = Hero(id="arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="noble_blade",
        name="Noble Blade",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=11,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        effect_id="noble_blade",
        effect_text="...",
        is_facedown=False,
    )
    hero.current_turn_card = card

    e1 = Hero(id="e1", name="E1", team=TeamColor.BLUE, deck=[], level=1)
    e2 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[e1], minions=[e2]),
        },
    )

    state.place_entity("arien", Hex(q=0, r=0, s=0))
    state.place_entity("e1", Hex(q=1, r=0, s=-1))  # Victim
    state.place_entity("m1", Hex(q=0, r=1, s=-1))  # Nudge Candidate (Adj to E1)

    state.current_actor_id = "arien"

    return state


def test_noble_blade_flow(noble_state):
    step = ResolveCardStep(hero_id="arien")
    push_steps(noble_state, [step])

    # 1. Choose Action
    req = process_resolution_stack(noble_state)
    assert req["type"] == "CHOOSE_ACTION"
    noble_state.execution_stack[-1].pending_input = {"choice_id": "ATTACK"}

    # 2. Select Attack Target (Mandatory)
    req = process_resolution_stack(noble_state)
    assert req["type"] == "SELECT_UNIT"
    assert "e1" in req["valid_options"]
    noble_state.execution_stack[-1].pending_input = {"selection": "e1"}

    # 3. Select Unit to Nudge (Optional)
    req = process_resolution_stack(noble_state)
    assert req["type"] == "SELECT_UNIT"
    # Filters Check:
    # - Must be adj to E1 (M1 is adj, Arien is adj)
    # - Must not be Self (Exclude Arien)
    # - Must not be Victim (Exclude E1)
    assert "m1" in req["valid_options"]
    assert "arien" not in req["valid_options"]
    assert "e1" not in req["valid_options"]

    noble_state.execution_stack[-1].pending_input = {"selection": "m1"}

    # 4. Select Dest for Nudge (Mandatory now)
    req = process_resolution_stack(noble_state)
    assert req["type"] == "SELECT_HEX"
    # M1 is at 0,1,-1.
    # Neighbors: 1,1,-2 (Empty), 0,0,0 (Arien), 1,0,-1 (E1)
    # Only 1,1,-2 is valid (OccupiedFilter)
    assert Hex(q=1, r=1, s=-2).model_dump() in req["valid_options"]
    noble_state.execution_stack[-1].pending_input = {
        "selection": {"q": 1, "r": 1, "s": -2}
    }

    # 5. Reaction Window (E1)
    req = process_resolution_stack(noble_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    noble_state.execution_stack[-1].pending_input = {"selected_card_id": "PASS"}

    # 6. Combat (Resolve)
    res = process_resolution_stack(noble_state)
    assert res is None  # Finished

    # Verify Nudge
    assert noble_state.entity_locations["m1"] == Hex(q=1, r=1, s=-2)

    # Verify Attack (E1 should be defeated? 4 dmg vs 0 def -> Defeated)
    # e1 should be removed from board or Defeat processed
    # If defeated, e1 not in locations
    assert "e1" not in noble_state.entity_locations


def test_noble_blade_skip(noble_state):
    step = ResolveCardStep(hero_id="arien")
    push_steps(noble_state, [step])

    # 1. Action
    process_resolution_stack(noble_state)
    noble_state.execution_stack[-1].pending_input = {"choice_id": "ATTACK"}

    # 2. Target
    process_resolution_stack(noble_state)
    noble_state.execution_stack[-1].pending_input = {"selection": "e1"}

    # 3. Nudge (Skip)
    req = process_resolution_stack(noble_state)
    assert req["can_skip"] == True
    noble_state.execution_stack[-1].pending_input = {"selection": "SKIP"}

    # 4. Reaction (Should jump straight here, skipping Hex Select and Place)
    req = process_resolution_stack(noble_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"  # Reaction Window
    noble_state.execution_stack[-1].pending_input = {"selected_card_id": "PASS"}

    # 5. End
    process_resolution_stack(noble_state)

    # Verify NO move
    assert noble_state.entity_locations["m1"] == Hex(q=0, r=1, s=-1)
