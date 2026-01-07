import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.rules import (
    validate_movement_path, is_immune, validate_attack_target,
    get_safe_zones_for_fast_travel
)

@pytest.fixture
def rules_state():
    board = Board()
    red_base_hex = Hex(q=0, r=0, s=0)
    zones = {"RedBase": Zone(id="RedBase", hexes={red_base_hex}, neighbors=[])}
    board.zones = zones
    board.populate_tiles_from_zones()
    
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[])},
        entity_locations={},
        active_zone_id="RedBase"
    )
    state.place_entity("h1", red_base_hex)
    return state

def test_validate_movement_path_edge_cases(rules_state):
    board = rules_state.board
    start = Hex(q=0, r=0, s=0)
    
    # start == end
    assert validate_movement_path(
        board=board, 
        start=start, 
        end=start, 
        max_steps=5
    ) is False
    
    # end is occupied (using place_entity to simulate)
    h2_hex = Hex(q=1, r=0, s=-1)
    rules_state.place_entity("h2", h2_hex)
    
    assert validate_movement_path(
        board=board, 
        start=start, 
        end=h2_hex, 
        max_steps=5
    ) is False
    
    # No path (blocked by obstacles)
    # Surround start with internal obstacles
    for adj in board.get_neighbors(start):
        # We need tiles to exist first if they are not in zones
        board.tiles[adj] = Tile(hex=adj, is_terrain=True)
    
    far_hex = Hex(q=2, r=0, s=-2)
    assert validate_movement_path(
        board=board, 
        start=start, 
        end=far_hex, 
        max_steps=10
    ) is False

def test_is_immune_edge_cases(rules_state):
    # Heavy minion check
    m_heavy = Minion(id="m_heavy", name="Heavy", type=MinionType.HEAVY, team=TeamColor.RED, is_heavy=True)
    rules_state.teams[TeamColor.RED].minions.append(m_heavy)
    
    # No active_zone_id
    rules_state.active_zone_id = None
    assert is_immune(m_heavy, rules_state) is False
    
    # Target is not minion
    h1 = rules_state.get_unit("h1")
    assert is_immune(h1, rules_state) is False
    
    # Zone not found
    rules_state.active_zone_id = "GhostZone"
    assert is_immune(m_heavy, rules_state) is False
    
    # Team not found
    m_heavy.team = TeamColor.BLUE # No BLUE team in fixture
    rules_state.active_zone_id = "RedBase"
    assert is_immune(m_heavy, rules_state) is False

def test_is_immune_success(rules_state):
    # Heavy minion check
    rules_state.remove_entity("h1")
    m_heavy = Minion(id="m_heavy", name="Heavy", type=MinionType.HEAVY, team=TeamColor.RED, is_heavy=True)
    rules_state.teams[TeamColor.RED].minions.append(m_heavy)
    rules_state.place_entity("m_heavy", Hex(q=0, r=0, s=0))
    
    # Another friendly minion in the same zone
    m_friend = Minion(id="m_friend", name="Friend", type=MinionType.MELEE, team=TeamColor.RED)
    rules_state.teams[TeamColor.RED].minions.append(m_friend)
    friend_hex = Hex(q=1, r=0, s=-1) # RedBase neighbor
    rules_state.place_entity("m_friend", friend_hex)
    
    # RedBase zone includes both hexes
    rules_state.board.zones["RedBase"].hexes.add(friend_hex)
    
    assert is_immune(m_heavy, rules_state) is True
    
    # If friend is NOT in the zone
    rules_state.place_entity("m_friend", Hex(q=10, r=10, s=-20))
    assert is_immune(m_heavy, rules_state) is False

def test_validate_movement_path_ignore_obstacles(rules_state):
    board = rules_state.board
    start = Hex(q=0, r=0, s=0)
    end = Hex(q=1, r=0, s=-1)
    
    board.tiles[end] = Tile(hex=end, is_terrain=True) # Obstacle
    
    # Normally False
    assert validate_movement_path(
        board=board, 
        start=start, 
        end=end, 
        max_steps=5, 
        ignore_obstacles=False
    ) is False
    # With ignore_obstacles=True, it should pass
    assert validate_movement_path(
        board=board, 
        start=start, 
        end=end, 
        max_steps=5, 
        ignore_obstacles=True
    ) is True

def test_validate_movement_path_obstacle_end(rules_state):
    board = rules_state.board
    start = Hex(q=0, r=0, s=0)
    end = Hex(q=1, r=0, s=-1)
    
    # End is occupied
    rules_state.place_entity("other_unit", end)
    assert validate_movement_path(
        board=board, 
        start=start, 
        end=end, 
        max_steps=5
    ) is False
    rules_state.remove_entity("other_unit")
    
    # End tile is terrain
    board.tiles[end] = Tile(hex=end, is_terrain=True) # Terrain is obstacle
    assert validate_movement_path(
        board=board, 
        start=start, 
        end=end, 
        max_steps=5
    ) is False
    
    # Neighbor is obstacle but not end
    mid = Hex(q=1, r=0, s=-1)
    end_ok = Hex(q=2, r=0, s=-2)
    board.tiles[mid] = Tile(hex=mid, is_terrain=True)
    # Clear end_ok to ensure it's not obstacle
    board.tiles[end_ok] = Tile(hex=end_ok, is_terrain=False)
    # Path blocked by mid
    assert validate_movement_path(
        board=board, 
        start=start, 
        end=end_ok, 
        max_steps=5
    ) is False

def test_validate_movement_path_dist_limit(rules_state):
    board = rules_state.board
    start = Hex(q=0, r=0, s=0)
    end = Hex(q=2, r=0, s=-2)
    
    # dist >= max_steps (path is 2 steps, max_steps is 1)
    assert validate_movement_path(
        board=board, 
        start=start, 
        end=end, 
        max_steps=1
    ) is False

def test_validate_attack_target_legacy_straight_line():
    attacker_pos = Hex(q=0, r=0, s=0)
    target_pos = Hex(q=1, r=1, s=-2) # Not a straight line
    
    # requires_straight_line = True
    # NOTE: validate_attack_target NO LONGER TAKES unit_locations
    assert validate_attack_target(
        attacker_pos=attacker_pos, 
        target_pos=target_pos, 
        range_val=5, 
        requires_straight_line=True
    ) is False
    
    # Out of range (fallback path)
    assert validate_attack_target(
        attacker_pos=attacker_pos, 
        target_pos=target_pos, 
        range_val=1, 
        requires_straight_line=False
    ) is False

def test_get_safe_zones_for_fast_travel_edge_cases(rules_state):
    # start_zone missing
    assert get_safe_zones_for_fast_travel(rules_state, TeamColor.RED, "GhostZone") == []
    
    # Candidate zone missing
    start_zone = rules_state.board.zones["RedBase"]
    start_zone.neighbors.append("MissingZone")
    # Should skip MissingZone and not crash
    safe = get_safe_zones_for_fast_travel(rules_state, TeamColor.RED, "RedBase")
    assert "RedBase" in safe
    assert "MissingZone" not in safe