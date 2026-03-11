import pytest
from goa2.domain.models.enums import FilterType
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.filters import (
    FilterCondition, TerrainFilter, RangeFilter, 
    TeamFilter, UnitTypeFilter, AdjacencyFilter, ImmunityFilter
)

@pytest.fixture
def extended_state():
    board = Board()
    # Create a small grid
    # (0,0,0) - Red Hero (h1)
    # (1,0,-1) - Blue Minion (m1, Melee)
    # (2,0,-2) - Blue Hero (h2)
    # (1,-1,0) - Empty Terrain
    # (0,1,-1) - Empty Non-Terrain
    # (3,0,-3) - Blue Heavy (m2) - Protected by m1
    
    hexes = [
        Hex(q=0, r=0, s=0), 
        Hex(q=1, r=0, s=-1), 
        Hex(q=2, r=0, s=-2), 
        Hex(q=1, r=-1, s=0),
        Hex(q=0, r=1, s=-1),
        Hex(q=3, r=0, s=-3)
    ]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
        
    board.tiles[Hex(q=1, r=-1, s=0)].is_terrain = True
    
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    h2 = Hero(id="h2", name="H2", team=TeamColor.BLUE, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)
    m2 = Minion(id="m2", name="M2", type=MinionType.HEAVY, team=TeamColor.BLUE)
    
    # Setup Zone for Immunity check
    mid_zone = Zone(id="Mid", label="Mid", hexes=set(hexes))
    board.zones["Mid"] = mid_zone
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[m1, m2])
        },
        entity_locations={},
        current_actor_id="h1",
        active_zone_id="Mid"
    )
    # Sync board occupancy
    state.place_entity("h1", Hex(q=0, r=0, s=0))
    state.place_entity("h2", Hex(q=2, r=0, s=-2))
    state.place_entity("m1", Hex(q=1, r=0, s=-1))
    state.place_entity("m2", Hex(q=3, r=0, s=-3))
        
    return state

def test_filter_condition_base():
    """Directly calling apply on base FilterCondition should raise NotImplementedError."""
    class DummyFilter(FilterCondition):
        pass
    
    f = DummyFilter(type=FilterType.OCCUPIED)
    with pytest.raises(NotImplementedError):
        f.apply(None, None, {})

def test_terrain_filter(extended_state):
    # Test True
    f_true = TerrainFilter(is_terrain=True)
    # (1,-1,0) is in board.tiles and marked as terrain
    assert f_true.apply(Hex(q=1, r=-1, s=0), extended_state, {}) is True
    # (0,0,0) is in board.tiles and NOT marked as terrain
    assert f_true.apply(Hex(q=0, r=0, s=0), extended_state, {}) is False
    
    # Test False
    f_false = TerrainFilter(is_terrain=False)
    assert f_false.apply(Hex(q=1, r=-1, s=0), extended_state, {}) is False
    # (0,1,-1) is in board.tiles and NOT marked as terrain
    assert f_false.apply(Hex(q=0, r=1, s=-1), extended_state, {}) is True
    
    # Missing tile (Virtual tile logic in Board.get_tile returns is_terrain=True)
    assert f_true.apply(Hex(q=99, r=99, s=-198), extended_state, {}) is True # Should be True as it's a virtual terrain tile

def test_range_filter_edge_cases(extended_state):
    # No current actor
    state_no_actor = extended_state.model_copy(update={"current_actor_id": None})
    f = RangeFilter(max_range=1)
    assert f.apply(Hex(q=1, r=0, s=-1), state_no_actor, {}) is False
    
    # Actor has no location
    state_no_loc = extended_state.model_copy(update={"entity_locations": {}})
    assert f.apply("m1", state_no_loc, {}) is False
    
    # Target has no location
    assert f.apply("non_existent_unit", extended_state, {}) is False
    
    # Custom origin
    f_origin = RangeFilter(max_range=1, origin_id="h2")
    assert f_origin.apply("m1", extended_state, {}) is True
    assert f_origin.apply("h1", extended_state, {}) is False # Dist 2

def test_team_filter_extended(extended_state):
    # FRIENDLY (Same team, not self)
    f_friendly = TeamFilter(relation="FRIENDLY")
    extended_state.current_actor_id = "h2"
    assert f_friendly.apply("m1", extended_state, {}) is True
    assert f_friendly.apply("h2", extended_state, {}) is False # Is self
    assert f_friendly.apply("h1", extended_state, {}) is False # Is enemy
    
    # SELF
    f_self = TeamFilter(relation="SELF")
    assert f_self.apply("h2", extended_state, {}) is True
    assert f_self.apply("m1", extended_state, {}) is False
    
    # Missing actor/target
    f_enemy = TeamFilter(relation="ENEMY")
    state_no_actor = extended_state.model_copy(update={"current_actor_id": None})
    assert f_enemy.apply("h1", state_no_actor, {}) is False
    assert f_enemy.apply("invalid_target", extended_state, {}) is False

def test_unit_type_filter_hero(extended_state):
    f_hero = UnitTypeFilter(unit_type="HERO")
    assert f_hero.apply("h1", extended_state, {}) is True
    assert f_hero.apply("m1", extended_state, {}) is False
    assert f_hero.apply(Hex(q=0, r=0, s=0), extended_state, {}) is False

def test_adjacency_filter(extended_state):
    # Setup: h1(Red) at (0,0,0), m1(Blue) at (1,0,-1)
    extended_state.current_actor_id = "h1"
    
    # Friendly Hero (None adjacent to h1)
    f_adj_friendly_hero = AdjacencyFilter(target_tags=["FRIENDLY", "HERO"])
    assert f_adj_friendly_hero.apply("h1", extended_state, {}) is False
    
    # Enemy Minion (m1 is adjacent to h1, Blue is enemy of Red)
    f_adj_enemy_minion = AdjacencyFilter(target_tags=["ENEMY", "MINION"])
    assert f_adj_enemy_minion.apply("h1", extended_state, {}) is True
    
    # Friendly Minion (m1 is adjacent to h2, both Blue)
    extended_state.current_actor_id = "h2"
    f_adj_friendly_minion = AdjacencyFilter(target_tags=["FRIENDLY", "MINION"])
    assert f_adj_friendly_minion.apply("h2", extended_state, {}) is True
    
    # Invalid candidate types
    assert f_adj_enemy_minion.apply(None, extended_state, {}) is False
    
    # Hex candidate (Hex (0,0,0) is adjacent to m1)
    extended_state.current_actor_id = "h1"
    assert f_adj_enemy_minion.apply(Hex(q=0, r=0, s=0), extended_state, {}) is True

def test_adjacency_filter_skip_immune(extended_state):
    """AdjacencyFilter with skip_immune=True should exclude hexes
    where the only adjacent enemies are immune."""
    extended_state.current_actor_id = "h1"
    # h1(Red) at (0,0,0), m1(Blue,Melee) at (1,0,-1), m2(Blue,Heavy) at (3,0,-3)
    # m2 is immune (heavy with m1 as support in same zone)
    # h2(Blue) at (2,0,-2) is NOT immune

    f_skip = AdjacencyFilter(target_tags=["ENEMY"], skip_immune=True)
    f_no_skip = AdjacencyFilter(target_tags=["ENEMY"])

    # (0,0,0) is adjacent to m1 (not immune) → both should pass
    assert f_no_skip.apply(Hex(q=0, r=0, s=0), extended_state, {}) is True
    assert f_skip.apply(Hex(q=0, r=0, s=0), extended_state, {}) is True

    # (2,0,-2) is adjacent to m2 (immune) AND m1 (not immune) → m1 makes it pass
    # But also h2 is at (2,0,-2) — it's the occupant, not a neighbor.
    # Neighbors of (2,0,-2): (1,0,-1)=m1, (3,0,-3)=m2
    assert f_no_skip.apply(Hex(q=2, r=0, s=-2), extended_state, {}) is True
    assert f_skip.apply(Hex(q=2, r=0, s=-2), extended_state, {}) is True  # m1 is not immune

    # Create a hex adjacent ONLY to m2 (immune heavy) — place a tile at (4,0,-4)
    # neighbors of (4,0,-4) include (3,0,-3)=m2 but no other occupied hexes
    new_hex = Hex(q=4, r=0, s=-4)
    extended_state.board.tiles[new_hex] = Tile(hex=new_hex)
    # Without skip_immune: passes (m2 is enemy)
    assert f_no_skip.apply(new_hex, extended_state, {}) is True
    # With skip_immune: fails (m2 is immune, no other adjacent enemy)
    assert f_skip.apply(new_hex, extended_state, {}) is False


def test_immunity_filter(extended_state):
    # m2 (Heavy) is protected by m1 (Melee) in the Mid zone.
    # m2 should be immune.
    f_immunity = ImmunityFilter()
    
    # m2 is immune, so apply() (which returns not rules.is_immune) should be False
    assert f_immunity.apply("m2", extended_state, {}) is False
    
    # m1 is not immune, so apply() should be True
    assert f_immunity.apply("m1", extended_state, {}) is True
    
    # h1 is not immune
    assert f_immunity.apply("h1", extended_state, {}) is True
    
    # Invalid candidate
    assert f_immunity.apply(Hex(q=0, r=0, s=0), extended_state, {}) is False
