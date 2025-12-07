import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import Team, TeamColor, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.domain.types import UnitID, BoardEntityID
from goa2.domain.tile import Tile
from goa2.engine.map_logic import check_lane_push_trigger, execute_push

@pytest.fixture
def map_state():
    # Lane: Z1 -> Z2 -> Z3
    z1 = Zone(id="Z1", hexes={Hex(q=0,r=0,s=0)})
    z2 = Zone(id="Z2", hexes={Hex(q=10,r=0,s=-10), Hex(q=11,r=0,s=-11)}) # 2 hexes in Z2
    z3 = Zone(id="Z3", hexes={Hex(q=20,r=0,s=-20)})
    
    b = Board(zones={"Z1": z1, "Z2": z2, "Z3": z3}, lane=["Z1", "Z2", "Z3"])
    b.populate_tiles_from_zones()
    
    s = GameState(board=b, teams={}, active_zone_id="Z2")
    
    # Teams
    t_red = Team(color=TeamColor.RED, heroes=[], minions=[])
    t_blue = Team(color=TeamColor.BLUE, heroes=[], minions=[])
    s.teams[TeamColor.RED] = t_red
    s.teams[TeamColor.BLUE] = t_blue
    
    return s

def test_push_trigger_conditions(map_state):
    s = map_state
    
    # helper
    def place_minion(team_col, uid, hex_coords):
        m = Minion(id=uid, type=MinionType.MELEE, team=team_col, name="M")
        s.teams[team_col].minions.append(m)
        s.unit_locations[uid] = hex_coords
        s.board.tiles[hex_coords].occupant_id = BoardEntityID(uid)
        
    h_z2_1 = Hex(q=10,r=0,s=-10)
    h_z2_2 = Hex(q=11,r=0,s=-11)
    
    # 1. Both Empty
    assert check_lane_push_trigger(s, "Z2") is None
    
    # 2. Red Present, Blue Empty -> Blue Loses? (Blue has 0)
    place_minion(TeamColor.RED, "mr1", h_z2_1)
    # Red: 1, Blue: 0 => Blue Loses (Red Pushes)
    assert check_lane_push_trigger(s, "Z2") == TeamColor.BLUE
    
    # 3. Both Present -> None (Contested)
    place_minion(TeamColor.BLUE, "mb1", h_z2_2)
    assert check_lane_push_trigger(s, "Z2") is None
    
    # 4. Red Dead (0), Blue Present -> Red Loses (Blue Pushes)
    # Remove Red Minion
    s.teams[TeamColor.RED].minions.pop()
    s.unit_locations.pop("mr1")
    s.board.tiles[h_z2_1].occupant_id = None
    
    assert check_lane_push_trigger(s, "Z2") == TeamColor.RED

def test_execute_push_red_loses(map_state):
    s = map_state
    # Current: Z2. Lane: [Z1, Z2, Z3]. RedBase=Left, BlueBase=Right.
    # Red Loses -> Battle moves TOWARDS Red Base (Left) -> Z1
    # Z2 index = 1. New index = 0 (Z1).
    
    # Setup some minions in Z2 to be wiped
    h_z2 = Hex(q=10,r=0,s=-10)
    m = Minion(id="to_wipe", type=MinionType.MELEE, team=TeamColor.BLUE, name="Survivor")
    s.teams[TeamColor.BLUE].minions.append(m)
    s.unit_locations["to_wipe"] = h_z2
    s.board.tiles[h_z2].occupant_id = BoardEntityID("to_wipe")
    
    execute_push(s, losing_team=TeamColor.RED)
    
    assert s.active_zone_id == "Z1"
    
    # Verify Wipe (Minions in old zone Z2 removed)
    assert "to_wipe" not in s.unit_locations
    assert len(s.teams[TeamColor.BLUE].minions) == 0
    assert s.board.tiles[h_z2].occupant_id is None

def test_execute_push_blue_loses(map_state):
    s = map_state
    # Blue Loses -> Battle moves TOWARDS Blue Base (Right) -> Z3
    execute_push(s, losing_team=TeamColor.BLUE)
    
    assert s.active_zone_id == "Z3"
