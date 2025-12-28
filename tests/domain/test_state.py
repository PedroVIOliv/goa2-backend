import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType, Card, CardColor, ActionType, CardTier, CardState
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

def test_hero_card_lifecycle():
    h1 = Hero(id="h1", name="H", team=TeamColor.RED, deck=[])
    c1 = Card(id="c1", name="C1", tier=CardTier.I, color=CardColor.RED, initiative=10, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t")
    c2 = Card(id="c2", name="C2", tier=CardTier.I, color=CardColor.BLUE, initiative=5, primary_action=ActionType.SKILL, effect_id="e", effect_text="t")
    
    h1.hand = [c1, c2]
    
    # 1. Play Card (Planning)
    h1.play_card(c1)
    
    assert c1 not in h1.hand
    assert c1.state == CardState.UNRESOLVED
    assert c1.is_facedown is True
    assert c1.played_this_round is True
    
    # 2. Discard (Defense or Cleanup)
    h1.discard_card(c2, from_hand=True)
    
    assert c2 not in h1.hand
    assert c2 in h1.discard_pile
    assert c2.state == CardState.DISCARD
    assert c2.is_facedown is False
    assert c2.played_this_round is False # Was discarded directly, not played
    
    # 3. Discard Already Played Card
    # Simulate resolution -> Discard
    h1.discard_card(c1, from_hand=False) # Skip hand check
    assert c1 in h1.discard_pile
    assert c1.state == CardState.DISCARD
    assert c1.played_this_round is True # Retains the flag! This is crucial for "Both Played and Discarded"

def test_retrieve_cards_logic():
    h1 = Hero(id="h1", name="H", team=TeamColor.RED, deck=[])
    c1 = Card(id="c1", name="C1", tier=CardTier.I, color=CardColor.RED, initiative=10, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t", played_this_round=True, state=CardState.DISCARD)
    c2 = Card(id="c2", name="C2", tier=CardTier.I, color=CardColor.BLUE, initiative=5, primary_action=ActionType.SKILL, effect_id="e", effect_text="t", played_this_round=True, state=CardState.RESOLVED)
    
    h1.discard_pile = [c1]
    h1.played_cards = [c2]
    h1.hand = []
    
    # Execute Retrieve
    h1.retrieve_cards()
    
    # Verify Hand
    assert len(h1.hand) == 2
    assert c1 in h1.hand
    assert c2 in h1.hand
    
    # Verify Piles Cleared
    assert len(h1.discard_pile) == 0
    assert len(h1.played_cards) == 0
    
    # Verify State Reset
    assert c1.state == CardState.HAND
    assert c1.played_this_round is False
    assert c2.state == CardState.HAND
    assert c2.played_this_round is False