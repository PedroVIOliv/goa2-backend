import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone, SpawnPoint, SpawnType
from goa2.domain.models import TeamColor, Team, Minion, MinionType, Token
from goa2.domain.hex import Hex
from goa2.domain.types import UnitID, BoardEntityID
from goa2.engine.mechanics import check_lane_push, perform_lane_push, run_end_phase
from goa2.engine.phases import GamePhase

@pytest.fixture
def basic_state():
    # Setup simple board: RedBase <-> Active <-> BlueBase
    z1 = Zone(id="red_base", hexes={Hex(q=0,r=0,s=0)})
    z2 = Zone(id="mid", hexes={Hex(q=1,r=-1,s=0), Hex(q=2,r=-2,s=0)})
    z3 = Zone(id="blue_base", hexes={Hex(q=3,r=-3,s=0)})
    
    board = Board(
        zones={"red_base": z1, "mid": z2, "blue_base": z3},
        lane=["red_base", "mid", "blue_base"],
        spawn_points=[
            SpawnPoint(location=Hex(q=0,r=0,s=0), team=TeamColor.RED, type=SpawnType.MINION, minion_type=MinionType.MELEE), # In Red Base
            SpawnPoint(location=Hex(q=1,r=-1,s=0), team=TeamColor.RED, type=SpawnType.MINION, minion_type=MinionType.MELEE), # In Mid
            SpawnPoint(location=Hex(q=3,r=-3,s=0), team=TeamColor.BLUE, type=SpawnType.MINION, minion_type=MinionType.MELEE) # In Blue Base
        ]
    )
    board.populate_tiles_from_zones()
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED),
            TeamColor.BLUE: Team(color=TeamColor.BLUE)
        },
        active_zone_id="mid"
    )
    return state

def test_lane_push_trigger_logic(basic_state):
    # Case 1: Both have 0 (Initial state) -> No Push (Ambiguous/Draw)
    assert check_lane_push(basic_state) is False
    
    # Case 2: Blue has 1, Red has 0 -> Push Triggered (Red Loses)
    # Add Blue Minion
    m_blue = Minion(id=UnitID("m_blue"), name="M", type=MinionType.MELEE, team=TeamColor.BLUE)
    basic_state.teams[TeamColor.BLUE].minions.append(m_blue)
    basic_state.unit_locations[m_blue.id] = Hex(q=1,r=-1,s=0) # In MID
    
    assert check_lane_push(basic_state) is True
    
    # Case 3: Both have 1 -> No Push
    m_red = Minion(id=UnitID("m_red"), name="M", type=MinionType.MELEE, team=TeamColor.RED)
    basic_state.teams[TeamColor.RED].minions.append(m_red)
    basic_state.unit_locations[m_red.id] = Hex(q=2,r=-2,s=0) # In MID
    
    assert check_lane_push(basic_state) is False

def test_perform_lane_push_execution(basic_state):
    # Setup: Red Loses Mid (0 Red, 1 Blue)
    m_blue = Minion(id=UnitID("m_blue"), name="M", type=MinionType.MELEE, team=TeamColor.BLUE)
    basic_state.teams[TeamColor.BLUE].minions.append(m_blue)
    basic_state.unit_locations[m_blue.id] = Hex(q=1,r=-1,s=0) # In MID
    
    # Initial Wave Counter
    assert basic_state.wave_counter == 5
    
    # Execute
    perform_lane_push(basic_state)
    
    # Verify:
    # 1. Wave Counter Decreased
    assert basic_state.wave_counter == 4
    
    # 2. Zone Shifted: Red Lost Mid -> Shift towards Red Base (Index - 1)
    # Lane: [RedBase, Mid, BlueBase]
    # Mid is idx 1. New idx 0 -> RedBase.
    assert basic_state.active_zone_id == "red_base"
    
    # 3. Old Minions Removed
    # m_blue was in Mid (Old Zone). Should be gone.
    assert m_blue.id not in basic_state.unit_locations
    assert len(basic_state.teams[TeamColor.BLUE].minions) == 0
    
    # 4. New Minions Spawned
    # New Zone is RedBase. Has a Red SpawnPoint.
    # Should spawn 1 Red Minion.
    assert len(basic_state.teams[TeamColor.RED].minions) == 1
    new_minion = basic_state.teams[TeamColor.RED].minions[0]
    assert basic_state.unit_locations[new_minion.id] == Hex(q=0,r=0,s=0)

def test_end_phase_mechanics(basic_state):
    # 1. Setup Token and Mock Unit on Tile
    tile_hex = Hex(q=1,r=-1,s=0)
    basic_state.board.tiles[tile_hex].occupant_id = BoardEntityID("token_1")
    # Note: "token_1" is NOT in unit_locations, so should be treated as Token
    
    # 2. Setup Unit with Marker (NOT IMPL YET IN TEST: Need Unit with markers list)
    # Just verify Token clearing for now.
    
    # 3. Setup Attrition
    # Red has 2, Blue has 1 in Active Zone. Diff = 1. Blue loses 1.
    z = basic_state.board.zones["mid"]
    
    m_r1 = Minion(id=UnitID("r1"), type=MinionType.MELEE, team=TeamColor.RED, name="R1")
    m_r2 = Minion(id=UnitID("r2"), type=MinionType.MELEE, team=TeamColor.RED, name="R2")
    m_b1 = Minion(id=UnitID("b1"), type=MinionType.MELEE, team=TeamColor.BLUE, name="B1")
    
    basic_state.teams[TeamColor.RED].minions.extend([m_r1, m_r2])
    basic_state.teams[TeamColor.BLUE].minions.append(m_b1)
    
    basic_state.unit_locations[m_r1.id] = list(z.hexes)[0]
    basic_state.unit_locations[m_r2.id] = list(z.hexes)[0] # Same hex?? Illegal but fine for count test
    basic_state.unit_locations[m_b1.id] = list(z.hexes)[0]
    
    # Run
    run_end_phase(basic_state)
    
    # Verify:
    # 1. Token Removed
    assert basic_state.board.tiles[tile_hex].occupant_id is None
    
    # 2. Attrition
    # Blue had 1, Red had 2. Diff 1. Blue (loser) loses 1.
    # Blue count should be 0.
    assert len(basic_state.teams[TeamColor.BLUE].minions) == 0
    assert len(basic_state.teams[TeamColor.RED].minions) == 2
    
    # 3. Round Advanced
    assert basic_state.round == 2
    assert basic_state.turn == 1
