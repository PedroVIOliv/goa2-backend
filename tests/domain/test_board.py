import pytest
from goa2.domain.board import Board, Zone, SpawnPoint, SpawnType
from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor, MinionType

def test_board_lookup_and_init():
    h1 = Hex(q=0, r=0, s=0)
    z1 = Zone(id="MZ", hexes={h1})
    b = Board(zones={"MZ": z1})
    
    # Test O(1) lookup
    # Should lazily build index on first call
    assert b.get_zone_for_hex(h1) == "MZ"
    
    # Test invalid hex
    assert b.get_zone_for_hex(Hex(q=10, r=0, s=-10)) is None

def test_spawn_points():
    h_hero = Hex(q=1, r=-1, s=0)
    h_minion = Hex(q=2, r=-2, s=0)
    
    sp1 = SpawnPoint(location=h_hero, team=TeamColor.RED) # Hero default
    sp2 = SpawnPoint(location=h_minion, team=TeamColor.BLUE, minion_type=MinionType.MELEE)
    
    b = Board(spawn_points=[sp1, sp2])
    
    found_sp1 = b.get_spawn_point(h_hero)
    assert found_sp1.is_hero_spawn
    assert not found_sp1.is_minion_spawn
    assert found_sp1.minion_type is None
    
    found_sp2 = b.get_spawn_point(h_minion)
    assert found_sp2.is_minion_spawn
    assert found_sp2.minion_type == MinionType.MELEE

def test_obstacles():
    obs = Hex(q=5, r=5, s=-10)
    b = Board(obstacles={obs})
    assert b.is_obstacle(obs)
    assert not b.is_obstacle(Hex(q=0,r=0,s=0))
