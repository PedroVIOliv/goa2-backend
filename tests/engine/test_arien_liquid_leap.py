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
)
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps


@pytest.fixture
def leap_state():
    board = Board()
    # 0,0,0: Origin (Hero)
    # 1,0,-1: Empty, No Spawn, Adj to Spawn (1,-1,0) -> INVALID
    # 2,0,-2: Empty, No Spawn, NOT Adj to Spawn -> VALID
    # 1,-1,0: Spawn Point (Empty) -> INVALID
    # 0,1,-1: Empty, No Spawn, NOT Adj to Spawn -> VALID
    # 2,-1,-1: Range 2, Adj to Spawn (1,-1,0) -> INVALID

    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=1, r=-1, s=0),
        Hex(q=0, r=1, s=-1),
        Hex(q=2, r=-1, s=-1),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    # Add a spawn point at 1,-1,0
    board.tiles[Hex(q=1, r=-1, s=0)].spawn_point = SpawnPoint(
        location=Hex(q=1, r=-1, s=0), team=TeamColor.RED, type=SpawnType.HERO
    )

    hero = Hero(id="hero_arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="liquid_leap",
        name="Liquid Leap",
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=4,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        is_ranged=True,
        range_value=2,
        effect_id="liquid_leap",
        effect_text="...",
        is_facedown=False,
    )
    hero.current_turn_card = card

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )
    state.place_entity("hero_arien", Hex(q=0, r=0, s=0))
    state.current_actor_id = "hero_arien"

    return state


def test_liquid_leap_filters(leap_state):
    step = ResolveCardStep(hero_id="hero_arien")
    push_steps(leap_state, [step])

    # 1. Select Action
    req = process_resolution_stack(leap_state)
    assert req["type"] == "CHOOSE_ACTION"
    leap_state.execution_stack[-1].pending_input = {"selection": "SKILL"}

    # 2. Select Hex
    req = process_resolution_stack(leap_state)
    assert req["type"] == "SELECT_HEX"

    valid_hexes = req["valid_options"]

    # expected: 2,0,-2 and 0,1,-1
    # 0,0,0 is usually excluded because OccupiedFilter(is_occupied=False)
    # but range filter might include it. OccupiedFilter will catch it.

    assert Hex(q=2, r=0, s=-2).model_dump() in valid_hexes
    assert Hex(q=0, r=1, s=-1).model_dump() in valid_hexes

    # invalid:
    assert Hex(q=1, r=0, s=-1).model_dump() not in valid_hexes  # Adj to empty spawn
    assert Hex(q=1, r=-1, s=0).model_dump() not in valid_hexes  # Is spawn
    assert Hex(q=2, r=-1, s=-1).model_dump() not in valid_hexes  # Adj to empty spawn
    assert Hex(q=0, r=0, s=0).model_dump() not in valid_hexes  # Occupied by self


def test_liquid_leap_execution(leap_state):
    step = ResolveCardStep(hero_id="hero_arien")
    push_steps(leap_state, [step])

    # 1. Select Action
    process_resolution_stack(leap_state)
    leap_state.execution_stack[-1].pending_input = {"selection": "SKILL"}

    # 2. Select Hex
    process_resolution_stack(leap_state)
    leap_state.execution_stack[-1].pending_input = {
        "selection": {"q": 2, "r": 0, "s": -2}
    }

    # 3. Finalize
    res = process_resolution_stack(leap_state)
    assert res is None

    # 4. Verify Position
    assert leap_state.entity_locations["hero_arien"] == Hex(q=2, r=0, s=-2)
