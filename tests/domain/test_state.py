import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequest, InputRequestType

@pytest.fixture
def populated_state():
    h1 = Hero(id="h1", name="Hero1", team=TeamColor.RED, deck=[])
    m1 = Minion(id="m1", name="Minion1", type=MinionType.MELEE, team=TeamColor.RED)
    
    # Create Board with necessary tiles
    start_hex = Hex(q=0, r=0, s=0)
    target_hex = Hex(q=1, r=0, s=-1)
    
    board = Board()
    board.tiles[start_hex] = Tile(hex=start_hex)
    board.tiles[target_hex] = Tile(hex=target_hex)
    
    # Pre-occupy start hex
    board.tiles[start_hex].occupant_id = "h1"
    
    return GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[m1]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        },
        unit_locations={"h1": start_hex}
    )

def test_get_lookup(populated_state):
    # Found
    assert populated_state.get_hero("h1") is not None
    assert populated_state.get_unit("h1") is not None
    assert populated_state.get_unit("m1") is not None
    
    # Not Found
    assert populated_state.get_hero("ghost") is None
    assert populated_state.get_unit("ghost") is None

def test_movement_logic(populated_state):
    # Move H1 to 1,0,-1
    target = Hex(q=1, r=0, s=-1)
    
    # Check Pre-condition
    assert "h1" in populated_state.unit_locations
    
    # Move
    populated_state.move_unit("h1", target)
    
    # Check Post-condition
    assert populated_state.unit_locations["h1"] == target
    assert populated_state.board.tiles[target].occupant_id == "h1"
    
    # Check Cleanup of old tile
    old = Hex(q=0, r=0, s=0)
    if old in populated_state.board.tiles:
        assert populated_state.board.tiles[old].occupant_id is None

def test_remove_unit(populated_state):
    populated_state.remove_unit("h1")
    assert "h1" not in populated_state.unit_locations
    # Tile check
    loc = Hex(q=0, r=0, s=0)
    if loc in populated_state.board.tiles:
        assert populated_state.board.tiles[loc].occupant_id is None

def test_awaiting_input_type():
    s = GameState(board=Board(), teams={})
    assert s.awaiting_input_type == InputRequestType.NONE
    
    s.input_stack.append(InputRequest(id="req1", request_type=InputRequestType.SELECT_UNIT, prompt="T", player_id="p1"))
    assert s.awaiting_input_type == InputRequestType.SELECT_UNIT
