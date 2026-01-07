import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, ActionType, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.steps import (
    MoveSequenceStep,
    FastTravelSequenceStep,
    MoveUnitStep,
    SelectStep,
    PlaceUnitStep,
)
from goa2.engine.handler import process_resolution_stack, push_steps


@pytest.fixture
def base_state():
    board = Board()
    # Setup zones first so populate_tiles_from_zones works
    z1 = Zone(id="z1", hexes={Hex(q=0, r=0, s=0)}, neighbors=["z2"])
    z2 = Zone(id="z2", hexes={Hex(q=1, r=0, s=-1)}, neighbors=["z1"])
    board.zones = {"z1": z1, "z2": z2}
    board.populate_tiles_from_zones()

    # Add some extra tiles for movement tests
    for q in range(-2, 3):
        for r in range(-2, 3):
            h = Hex(q=q, r=r, s=-q - r)
            if h not in board.tiles:
                board.tiles[h] = Tile(hex=h)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_red",
    )

    hero = Hero(id="hero_red", name="Hero Red", team=TeamColor.RED, deck=[])
    state.teams[TeamColor.RED].heroes.append(hero)
    state.place_entity("hero_red", Hex(q=0, r=0, s=0))

    return state


def test_move_sequence_spawns_selection(base_state):
    # Setup: Hero at 0,0,0. Move range 1.
    step = MoveSequenceStep(unit_id="hero_red", range_val=1)
    push_steps(base_state, [step])

    # Process
    req = process_resolution_stack(base_state)

    assert req is not None
    assert req["type"] == "SELECT_HEX"
    assert "Select Movement Destination" in req["prompt"]
    # Neighbors of 0,0,0 are 6. Plus the current hex makes 7.
    assert len(req["valid_options"]) == 7


def test_move_sequence_skips_selection_with_key(base_state):
    # Setup: Destination already in context
    base_state.execution_context["target_hex"] = Hex(q=1, r=0, s=-1)
    step = MoveSequenceStep(unit_id="hero_red", range_val=1)
    push_steps(base_state, [step])

    req = process_resolution_stack(base_state)

    assert req is None  # No input needed
    assert base_state.entity_locations["hero_red"] == Hex(q=1, r=0, s=-1)


def test_move_sequence_range_zero_only_current_hex(base_state):
    # If range is 0, only the current hex should be a valid candidate
    step = MoveSequenceStep(unit_id="hero_red", range_val=0)
    push_steps(base_state, [step])

    req = process_resolution_stack(base_state)

    assert req is not None
    assert len(req["valid_options"]) == 1
    assert req["valid_options"][0] == Hex(q=0, r=0, s=0)


def test_fast_travel_sequence_flow(base_state):
    # Already has safe zones z1, z2 from fixture
    # No enemies, so both zones are safe

    step = FastTravelSequenceStep(unit_id="hero_red")
    push_steps(base_state, [step])

    req = process_resolution_stack(base_state)

    assert req is not None
    assert req["type"] == "SELECT_HEX"
    # Valid options should be Hex(1,0,-1) because Hex(0,0,0) is occupied by self
    assert len(req["valid_options"]) == 1
    assert req["valid_options"][0] == Hex(q=1, r=0, s=-1)


def test_fast_travel_sequence_skips_selection_with_key(base_state):
    # Setup: Destination already in context
    base_state.execution_context["target_hex"] = Hex(q=1, r=0, s=-1)
    step = FastTravelSequenceStep(unit_id="hero_red")
    push_steps(base_state, [step])

    req = process_resolution_stack(base_state)

    assert req is None
    assert base_state.entity_locations["hero_red"] == Hex(q=1, r=0, s=-1)


def test_move_sequence_obstacle_pathfinding(base_state):
    # Setup: Hero at (-1, 0, 1). Goal (1, 0, -1).
    # Center (0, 0, 0) is an obstacle.
    # Distance around the center is 3. Direct through center is 2 (but blocked).

    start = Hex(q=-1, r=0, s=1)
    target = Hex(q=1, r=0, s=-1)
    center = Hex(q=0, r=0, s=0)

    # Ensure center is obstacle
    base_state.board.get_tile(center).is_terrain = True

    # Move hero to start
    base_state.place_entity("hero_red", start)

    # Case 1: Movement range 2
    step_2 = MoveSequenceStep(unit_id="hero_red", range_val=2)
    push_steps(base_state, [step_2])
    req_2 = process_resolution_stack(base_state)

    assert req_2 is not None
    # target should NOT be in options
    assert target not in req_2["valid_options"]

    # Case 2: Movement range 3
    base_state.execution_stack.clear()
    step_3 = MoveSequenceStep(unit_id="hero_red", range_val=3)
    push_steps(base_state, [step_3])
    req_3 = process_resolution_stack(base_state)

    assert req_3 is not None
    # target SHOULD be in options. Plus neighbors, plus current hex.
    assert target in req_3["valid_options"]
    assert start in req_3["valid_options"]


def test_move_sequence_always_allows_current_hex(base_state):
    # Setup: Hero at (0,0,0). Range 2.
    # Current code blocks (0,0,0) if range > 0 because of OccupiedFilter.
    # We want it to be selectable.
    start = Hex(q=0, r=0, s=0)
    step = MoveSequenceStep(unit_id="hero_red", range_val=2)
    push_steps(base_state, [step])

    req = process_resolution_stack(base_state)

    assert req is not None
    # start (0,0,0) SHOULD be in valid options even though range > 0
    assert start in req["valid_options"]
