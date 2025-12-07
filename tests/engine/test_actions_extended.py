import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, MinionType
from goa2.domain.hex import Hex
from goa2.domain.types import UnitID, BoardEntityID
from goa2.domain.tile import Tile
from goa2.engine.actions import SpawnMinionCommand

@pytest.fixture
def empty_state():
    b = Board()
    state = GameState(board=b, teams={})
    # Pre-create Hex in Tiles to simulate valid map
    h = Hex(q=0,r=0,s=0)
    state.board.tiles[h] = Tile(hex=h)
    return state

def test_spawn_minion_success(empty_state):
    s = empty_state
    loc = Hex(q=0,r=0,s=0)
    uid = UnitID("m1")
    
    cmd = SpawnMinionCommand(location=loc, minion_type=MinionType.HEAVY, team=TeamColor.RED, unit_id=uid)
    cmd.execute(s)
    
    # 1. Check Team creation & Minion list
    assert TeamColor.RED in s.teams
    assert len(s.teams[TeamColor.RED].minions) == 1
    m = s.teams[TeamColor.RED].minions[0]
    assert m.id == uid
    assert m.type == MinionType.HEAVY
    
    # 2. Check Global Lookups
    assert s.unit_locations[uid] == loc
    
    # 3. Check Tile Occupancy
    assert s.board.tiles[loc].occupant_id == BoardEntityID(uid)
    assert s.board.tiles[loc].is_occupied

def test_spawn_minion_occupied_failure(empty_state):
    s = empty_state
    loc = Hex(q=0,r=0,s=0)
    
    # Occupy it manually
    s.unit_locations["blocker"] = loc
    # (Command checks unit_locations.values(), not just tiles for now, for robustness)
    
    with pytest.raises(ValueError, match="occupied"):
        SpawnMinionCommand(loc, MinionType.MELEE, TeamColor.BLUE, UnitID("m2")).execute(s)
