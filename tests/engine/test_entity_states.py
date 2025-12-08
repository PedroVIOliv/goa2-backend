import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import TeamColor, Team, Minion, MinionType, ActionType
from goa2.domain.hex import Hex
from goa2.domain.types import UnitID, BoardEntityID
from goa2.engine.rules import is_immune, validate_target
from goa2.engine.mechanics import enforce_minion_bounding

@pytest.fixture
def entity_state():
    # Board with BattleZone and OutZone
    z_battle = Zone(id="battle", hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=-1,s=0)})
    z_void = Zone(id="void", hexes={Hex(q=9,r=9,s=-18)})
    
    board = Board(
        zones={"battle": z_battle, "void": z_void},
        lane=["battle"],
        tiles={} # Populated below
    )
    board.populate_tiles_from_zones()
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, life_counters=5),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, life_counters=5)
        },
        active_zone_id="battle",
        unit_locations={}
    )
    return state

def test_heavy_immunity(entity_state):
    # Setup: Heavy Minion + Friendly Minion -> Immune
    heavy = Minion(id=UnitID("heavy"), type=MinionType.HEAVY, team=TeamColor.RED, name="H")
    friend = Minion(id=UnitID("friend"), type=MinionType.MELEE, team=TeamColor.RED, name="F")
    enemy = Minion(id=UnitID("enemy"), type=MinionType.MELEE, team=TeamColor.BLUE, name="E")
    
    entity_state.teams[TeamColor.RED].minions.extend([heavy, friend])
    entity_state.teams[TeamColor.BLUE].minions.append(enemy)
    
    # Place in BattleZone
    entity_state.unit_locations[heavy.id] = Hex(q=0,r=0,s=0)
    entity_state.unit_locations[friend.id] = Hex(q=1,r=-1,s=0)
    entity_state.unit_locations[enemy.id] = Hex(q=0,r=0,s=0) # Same hex (illegal usually) but okay for test
    
    # 1. Check Immunity
    assert is_immune(heavy, entity_state) is True
    
    # 2. Check Validation
    # Enemy tries to target Heavy
    # Range 1. Distance is 0 (same hex) or 1.
    valid = validate_target(
        source=enemy,
        target=heavy, 
        action_type=ActionType.ATTACK,
        state=entity_state, 
        range_val=1
    )
    assert valid is False # Blocked by Immunity
    
    # 3. Remove Friend
    entity_state.teams[TeamColor.RED].minions.remove(friend)
    del entity_state.unit_locations[friend.id]
    
    # 4. Check Immunity Gone
    assert is_immune(heavy, entity_state) is False
    
    valid = validate_target(
        source=enemy,
        target=heavy, 
        action_type=ActionType.ATTACK,
        state=entity_state, 
        range_val=1
    )
    assert valid is True

def test_minion_bounding_rule(entity_state):
    # Setup: Minion currently in Void (Out of Bounds)
    minion = Minion(id=UnitID("lost"), type=MinionType.MELEE, team=TeamColor.RED, name="Lost")
    entity_state.teams[TeamColor.RED].minions.append(minion)
    
    void_hex = Hex(q=9,r=9,s=-18)
    entity_state.unit_locations[minion.id] = void_hex
    
    # Ensure BattleZone has empty space
    target_hex = Hex(q=0,r=0,s=0)
    # Ensure it's empty
    assert entity_state.board.tiles[target_hex].occupant_id is None
    
    # Execute Bounding
    enforce_minion_bounding(entity_state, minion.id)
    
    # Verify: Minion moved to A valid hex in the zone
    # Our simple logic sorted by distance from current_loc.
    # q=9,r=9 is far. Both hexes in battle zone are closer.
    # Distance from (9,9,-18) to (0,0,0) is 9.
    # Distance from (9,9,-18) to (1,-1,0) is also large 
    # (dist((9,9,-18), (1,-1,0)) = max(|9-1|, |9-(-1)|, |-18-0|) / 2 ? No.
    # Hex distance: 
    # a=(9,9,-18), b=(0,0,0) -> diff=(9,9,-18). max(abs) = 18. dist = 18/2?? No, formula is max(|dq|, |dr|, |ds|).
    # so dist is 18 if coords are normalized (sum=0).
    # d((9,9,-18), (0,0,0)) -> max(9,9,18) = 18.
    # d((9,9,-18), (1,-1,0)) -> diff=(8, 10, -18). max(8,10,18) = 18.
    # Both are distance 18.
    # So "nearest" is ambiguous. Sort is unstable or implicit order.
    # We should just assert new_loc IS IN battle_zone.hexes
    
    new_loc = entity_state.unit_locations.get(minion.id)
    new_loc = entity_state.unit_locations.get(minion.id)
    assert new_loc in entity_state.board.zones["battle"].hexes
    assert entity_state.board.tiles[new_loc].occupant_id == str(minion.id)
    
    # Verify: Old tile cleared
    # (Since we didn't populate tile for void in this mock setup fully, just check unit_loc)
    assert void_hex not in entity_state.unit_locations.values() # Wait, unit_locs has ID -> Hex.
    assert entity_state.unit_locations[minion.id] != void_hex

def test_team_life_counters(entity_state):
    # Verify Life Counter Exists
    assert entity_state.teams[TeamColor.RED].life_counters == 5
    
    # Simulate Death Penalty (Manual update as no command yet)
    entity_state.teams[TeamColor.RED].life_counters -= 1
    assert entity_state.teams[TeamColor.RED].life_counters == 4
