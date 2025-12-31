import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.map_logic import (
    check_lane_push_trigger, get_push_target_zone_id, 
    count_enemies, find_nearest_empty_hexes
)

@pytest.fixture
def map_state():
    board = Board()
    
    # zones: 
    # RedBase (0,0,0)
    # Mid (1,0,-1), (1,-1,0)
    # BlueBase (2,-1,-1)
    # Jungle (0,1,-1)
    
    red_base_hex = Hex(q=0, r=0, s=0)
    mid_hexes = {Hex(q=1, r=0, s=-1), Hex(q=1, r=-1, s=0)}
    blue_base_hex = Hex(q=2, r=-1, s=-1)
    jungle_hex = Hex(q=0, r=1, s=-1)
    
    zones = {
        "RedBase": Zone(id="RedBase", label="RedBase", hexes={red_base_hex}),
        "Mid": Zone(id="Mid", label="Mid", hexes=mid_hexes),
        "BlueBase": Zone(id="BlueBase", label="BlueBase", hexes={blue_base_hex}),
        "Jungle": Zone(id="Jungle", label="Jungle", hexes={jungle_hex})
    }
    board.zones = zones
    board.populate_tiles_from_zones()
    board.lane = ["RedBase", "Mid", "BlueBase"]
    
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    h2 = Hero(id="h2", name="H2", team=TeamColor.BLUE, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.RED)
    m2 = Minion(id="m2", name="M2", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[m1]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[m2])
        },
        unit_locations={
            "h1": red_base_hex,
            "m1": Hex(q=1, r=0, s=-1), # Mid
            "h2": blue_base_hex,
            "m2": Hex(q=1, r=-1, s=0)  # Mid
        },
        active_zone_id="Mid"
    )
    
    # Sync board occupancy
    for uid, loc in state.unit_locations.items():
        board.get_tile(loc).occupant_id = uid
        
    return state

def test_check_lane_push_trigger_edge_cases(map_state):
    # Missing active_zone_id
    map_state.active_zone_id = None
    assert check_lane_push_trigger(map_state, None) is None
    
    # Non-existent zone
    assert check_lane_push_trigger(map_state, "Unknown") is None

def test_get_push_target_zone_id_edge_cases(map_state):
    # No active_zone_id in state
    map_state.active_zone_id = None
    assert get_push_target_zone_id(map_state, TeamColor.RED) == (None, False)
    
    # Current zone not in lane
    map_state.active_zone_id = "Jungle"
    assert get_push_target_zone_id(map_state, TeamColor.RED) == (None, False)
    
    # Red Loses Base (Game Over)
    map_state.active_zone_id = "RedBase"
    target, is_over = get_push_target_zone_id(map_state, TeamColor.RED)
    assert target is None
    assert is_over is True
    
    # Blue Loses Base (Game Over)
    map_state.active_zone_id = "BlueBase"
    target, is_over = get_push_target_zone_id(map_state, TeamColor.BLUE)
    assert target is None
    assert is_over is True

def test_count_enemies_extended(map_state):
    # Red's perspective in Mid
    # Hostiles: h2 (Blue hero), m2 (Blue minion)
    # Note: h2 is in BlueBase, m2 is in Mid.
    # So in Mid, Red sees 1 enemy (m2).
    assert count_enemies(map_state, "Mid", TeamColor.RED) == 1
    
    # Move h2 to Mid
    map_state.unit_locations["h2"] = Hex(q=1, r=0, s=-1)
    # Now Red sees 2 enemies in Mid (m2 and h2)
    assert count_enemies(map_state, "Mid", TeamColor.RED) == 2
    
    # Non-existent zone
    assert count_enemies(map_state, "Unknown", TeamColor.RED) == 0

def test_find_nearest_empty_hexes_extended(map_state):
    # Non-existent zone
    assert find_nearest_empty_hexes(map_state, Hex(q=0,r=0,s=0), "Unknown") == []
    
    # All hexes in Mid are occupied
    # Mid hexes: (1,0,-1) - m1 (or h2 from prev test), (1,-1,0) - m2
    # Reset locations for clarity
    map_state.unit_locations = {
        "m1": Hex(q=1, r=0, s=-1),
        "m2": Hex(q=1, r=-1, s=0)
    }
    # Update board occupants
    for tile in map_state.board.tiles.values(): tile.occupant_id = None
    map_state.board.get_tile(Hex(q=1, r=0, s=-1)).occupant_id = "m1"
    map_state.board.get_tile(Hex(q=1, r=-1, s=0)).occupant_id = "m2"
    
    # Starting from (1,0,-1), look for empty in Mid
    # Neighbors of (1,0,-1) are (1,-1,0), (2,-1,-1), (2,0,-2), (1,1,-2), (0,1,-1), (0,0,0)
    # Only (1,-1,0) is in Mid, but it's occupied.
    # So there are NO empty hexes in Mid.
    assert find_nearest_empty_hexes(map_state, Hex(q=1, r=0, s=-1), "Mid") == []

def test_find_nearest_empty_hexes_optimization_break(map_state):
    # Create a larger zone to trigger the early break when a layer is found
    h_center = Hex(q=0, r=0, s=0)
    h_ring1 = h_center.neighbors()
    
    zone_hexes = {h_center} | set(h_ring1)
    map_state.board.zones["Large"] = Zone(id="Large", label="Large", hexes=zone_hexes)
    map_state.board.populate_tiles_from_zones()
    
    # Occupy the center
    map_state.board.get_tile(h_center).occupant_id = "some_id"
    
    # Start from center. Distance 1 layer has 6 empty hexes.
    # The BFS should find all 6 at dist 1 and then STOP (break loop) before dist 2.
    candidates = find_nearest_empty_hexes(map_state, h_center, "Large")
    assert len(candidates) == 6
    for h in h_ring1:
        assert h in candidates
