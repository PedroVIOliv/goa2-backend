import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveDisplacementStep
from goa2.engine.handler import process_resolution_stack, push_steps


@pytest.fixture
def displacement_state():
    board = Board()
    # Zone 1
    z1 = Zone(
        id="z1",
        name="Battle",
        hexes=[
            Hex(q=0, r=0, s=0),  # Spawn (Blocked)
            Hex(q=1, r=0, s=-1),  # Empty (Option 1)
            Hex(q=1, r=-1, s=0),  # Occupied (Block)
            Hex(q=2, r=0, s=-2),  # Far (Should not be picked)
        ],
    )
    board.zones["z1"] = z1

    for h in z1.hexes:
        board.tiles[h] = Tile(hex=h)

    # Blockers
    h1 = Hero(id="h1", name="Blocker", team=TeamColor.RED, deck=[])  # Blocks Spawn
    m_block = Minion(
        id="m_block", name="Blocker2", type=MinionType.MELEE, team=TeamColor.RED
    )  # Blocks neighbor

    # Displaced Unit (Not on board yet)
    m_disp = Minion(
        id="m_disp", name="Displaced", type=MinionType.MELEE, team=TeamColor.RED
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[h1], minions=[m_block, m_disp]
            ),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        entity_locations={},
        active_zone_id="z1",
        tie_breaker_team=TeamColor.RED,
    )
    # Sync board
    state.place_entity("h1", Hex(q=0, r=0, s=0))
    state.place_entity("m_block", Hex(q=1, r=-1, s=0))

    return state


def test_displacement_auto_select(displacement_state):
    # m_disp is displaced from (0,0,0).
    # (0,0,0) is blocked.
    # Neighbors:
    # (1,0,-1) -> Empty (Dist 1).
    # (1,-1,0) -> Occupied (Dist 1).
    # (0,1,-1) -> Not in Zone (assumed, BFS checks zone).
    # So valid candidate is (1,0,-1).

    origin = Hex(q=0, r=0, s=0)
    step = ResolveDisplacementStep(displacements=[("m_disp", origin)])
    push_steps(displacement_state, [step])

    # Run
    # Step 1: ResolveDisplacement -> Detects 1 Candidate -> Spawns PlaceUnitStep + Recursive Step
    process_resolution_stack(displacement_state)

    # Step 2: PlaceUnitStep runs
    process_resolution_stack(displacement_state)

    # Step 3: Recursive ResolveDisplacement (empty list) -> finishes
    process_resolution_stack(displacement_state)

    # Assert
    final_loc = displacement_state.entity_locations.get("m_disp")
    assert final_loc == Hex(q=1, r=0, s=-1)


def test_displacement_prompt(displacement_state):
    # Free up the other neighbor to force a choice
    # Clear (1,-1,0)
    blocker_hex = Hex(q=1, r=-1, s=0)
    displacement_state.remove_entity("m_block")

    origin = Hex(q=0, r=0, s=0)
    step = ResolveDisplacementStep(displacements=[("m_disp", origin)])
    push_steps(displacement_state, [step])

    # Run
    req = process_resolution_stack(displacement_state)

    # Should request input
    assert req is not None
    assert req["type"] == "SELECT_HEX"
    assert len(req["valid_hexes"]) == 2
    assert Hex(q=1, r=0, s=-1).model_dump() in req["valid_hexes"]
    assert Hex(q=1, r=-1, s=0).model_dump() in req["valid_hexes"]

    # Provide Input
    target = Hex(q=1, r=-1, s=0)
    displacement_state.execution_stack[-1].pending_input = {
        "selection": target.model_dump()
    }
    process_resolution_stack(displacement_state)

    # Should spawn placement
    process_resolution_stack(displacement_state)  # PlaceUnit

    assert displacement_state.entity_locations.get("m_disp") == target


def test_displacement_multi_unit_selection(displacement_state):
    # Scenario: 2 Minions displaced from same spot.
    # m_disp is already there. Add m_disp_2.
    m_disp_2 = Minion(
        id="m_disp_2", name="Displaced2", type=MinionType.MELEE, team=TeamColor.RED
    )
    displacement_state.teams[TeamColor.RED].minions.append(m_disp_2)

    origin = Hex(q=0, r=0, s=0)
    # Queue both
    step = ResolveDisplacementStep(
        displacements=[("m_disp", origin), ("m_disp_2", origin)]
    )
    push_steps(displacement_state, [step])

    # Run 1: Should prompt for UNIT SELECTION
    req = process_resolution_stack(displacement_state)
    assert req is not None
    assert req["type"] == "SELECT_UNIT"
    assert "m_disp" in req["valid_options"]
    assert "m_disp_2" in req["valid_options"]

    # Input: Select m_disp_2 first
    displacement_state.execution_stack[-1].pending_input = {
        "selected_unit_id": "m_disp_2"
    }

    # Run 2: Spawns recursive steps. Resolve(m_disp_2) runs.
    # It sees 1 candidate (1,0,-1). Auto-places m_disp_2.
    # It returns new steps [PlaceUnit(m_disp_2), ResolveDisplacement(remaining)]
    # PlaceUnit runs.
    process_resolution_stack(displacement_state)  # Resolve(Input) -> Spawns Split
    process_resolution_stack(displacement_state)  # Resolve(m_disp_2) -> Spawns Place
    process_resolution_stack(displacement_state)  # PlaceUnit(m_disp_2)

    assert displacement_state.entity_locations.get("m_disp_2") == Hex(q=1, r=0, s=-1)

    # Run 3: ResolveDisplacement(remaining=[m_disp]) runs.
    # Now (1,0,-1) is OCCUPIED by m_disp_2.
    # So it should find next nearest... (0,1,-1)?
    # Wait, my fixture only has (1,0,-1) [Empty] and (1,-1,0) [Occupied by m_block].
    # So m_disp has NO range 1 options!
    # It should look for Range 2. (2,0,-2) is in fixture and empty.

    process_resolution_stack(displacement_state)  # Resolve(m_disp)
    # Spawns PlaceUnit(m_disp) at (2,0,-2) (Auto-select)
    process_resolution_stack(displacement_state)  # PlaceUnit

    assert displacement_state.entity_locations.get("m_disp") == Hex(q=2, r=0, s=-2)
