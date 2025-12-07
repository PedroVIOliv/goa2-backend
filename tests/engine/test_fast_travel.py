import pytest
from goa2.domain.state import GameState, InputRequestType
from goa2.engine.phases import GamePhase
from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ResolveNextCommand, ChooseActionCommand, PerformMovementCommand
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType
from goa2.domain.types import HeroID, CardID, UnitID
from goa2.domain.hex import Hex

@pytest.fixture
def fast_travel_state():
    b = Board()
    c = Card(
        id=CardID("c_move"), name="Dash", tier=CardTier.UNTIERED, color=CardColor.GOLD, 
        initiative=5, primary_action=ActionType.MOVEMENT, 
        effect_id="1", effect_text="Move"
    )
    # Card should have FAST_TRAVEL automatically added
    
    h = Hero(id=HeroID("h1"), name="Hero", team=TeamColor.RED, deck=[], hand=[c])
    t = Team(color=TeamColor.RED, heroes=[h])
    
    s = GameState(board=b, teams={TeamColor.RED: t}, phase=GamePhase.PLANNING)
    s.unit_locations[UnitID("h1")] = Hex(q=0,r=0,s=0)
    return s

def test_choose_fast_travel(fast_travel_state):
    s = fast_travel_state
    
    # Play
    PlayCardCommand(HeroID("h1"), CardID("c_move")).execute(s)
    RevealCardsCommand().execute(s)
    
    # Resolve -> Waiting for Choice
    ResolveNextCommand().execute(s)
    assert s.awaiting_input_type == InputRequestType.ACTION_CHOICE
    
    # Choose FAST_TRAVEL (Secondary)
    # Should work because of invalidator logic
    ChooseActionCommand(ActionType.FAST_TRAVEL).execute(s)
    
    # Should now be waiting for Hex (since Fast Travel replaces Move)
    assert s.awaiting_input_type == InputRequestType.MOVEMENT_HEX
    
    # Move
    PerformMovementCommand(Hex(q=1, r=-1, s=0)).execute(s)
    
    # Done
    assert s.phase == GamePhase.SETUP
    assert s.unit_locations[UnitID("h1")] == Hex(q=1, r=-1, s=0)
