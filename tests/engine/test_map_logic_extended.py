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
        entity_locations={},
        active_zone_id="Mid"
    )
    # Use Unified Placement
    state.place_entity("h1", red_base_hex)
    state.place_entity("m1", Hex(q=1, r=0, s=-1))
    state.place_entity("h2", blue_base_hex)
    state.place_entity("m2", Hex(q=1, r=-1, s=0))
    
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
    
    # Move h2 to Mid using Unified Placement
    map_state.place_entity("h2", Hex(q=1, r=0, s=-1)) # Note: This overwrites m1!
    
    # Wait, overwriting m1 means m1 is removed.
    # m1 was Red. h2 is Blue.
    # Now in Mid: m2 (Blue) and h2 (Blue).
    # Red sees 2 enemies.
    assert count_enemies(map_state, "Mid", TeamColor.RED) == 2
    
    # Non-existent zone
    assert count_enemies(map_state, "Unknown", TeamColor.RED) == 0

def test_find_nearest_empty_hexes_extended(map_state):
    # Non-existent zone
    assert find_nearest_empty_hexes(map_state, Hex(q=0,r=0,s=0), "Unknown") == []
    
    # All hexes in Mid are occupied
    # Mid hexes: (1,0,-1) - m1, (1,-1,0) - m2
    
    # Reset locations by placing entities exactly where they need to be
    # Note: Previous test might have moved things. Reset state if needed, but here we just set explicitly.
    map_state.place_entity("m1", Hex(q=1, r=0, s=-1))
    map_state.place_entity("m2", Hex(q=1, r=-1, s=0))
    
    # Ensure no other residuals (h2 was moved to (1,0,-1) in prev test)
    # place_entity("m1", ...) overwrote h2 at that location. h2 is now "limbo"? No, h2 is removed from board.
    # Wait, place_entity logic:
    # 3. Update New Tile Cache: target_tile.occupant_id = entity_id
    # But does it clear the OLD occupant? Yes, implicit overwrite. 
    # But does it update the OLD occupant's record? No.
    # Logic in state.py:
    # _set_location(entity_id, target_hex):
    #   1. Clear old location of entity_id.
    #   2. Update entity_id location.
    #   3. Update target_hex occupant.
    # It does NOT check if target_hex was already occupied by SOMEONE ELSE.
    # So if I put m1 where h2 was, h2 still thinks it's there in `entity_locations`.
    # This creates a "Ghost" in the dictionary (h2 -> hex) but board says (hex -> m1).
    # This is a nuance. `place_entity` overwrites the BOARD but doesn't evict the previous tenant from the dictionary.
    # However, `find_nearest_empty_hexes` checks `board.tiles`.
    
    # Let's cleanly remove h2 to be safe for this test logic assumption.
    map_state.remove_entity("h2")
    
    # Starting from (1,0,-1), look for empty in Mid
    # Only (1,-1,0) is in Mid, but it's occupied by m2.
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
    map_state.place_entity("some_id", h_center)
    
    # Start from center. Distance 1 layer has 6 empty hexes.
    # The BFS should find all 6 at dist 1 and then STOP (break loop) before dist 2.
    candidates = find_nearest_empty_hexes(map_state, h_center, "Large")
    assert len(candidates) == 6
    for h in h_ring1:
        assert h in candidates
