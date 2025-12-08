from goa2.domain.models import Hero, Card, CardTier, CardColor, ActionType, CardState, Team, TeamColor
from goa2.engine.actions import PlayCardCommand, ResolveNextCommand, ChooseActionCommand, PerformMovementCommand, PlayDefenseCommand
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.types import HeroID, CardID
from goa2.domain.hex import Hex
from goa2.engine.phases import GamePhase
import pytest

@pytest.fixture
def state_wrapper():
    # Setup simple state
    b = Board()
    card = Card(
        id="c1", 
        name="Test", 
        tier=CardTier.I, 
        color=CardColor.RED, 
        initiative=10, 
        primary_action=ActionType.MOVEMENT,
        primary_action_value=1,
        secondary_actions={ActionType.HOLD: 0},
        effect_id="", effect_text="",
        state=CardState.DECK # Default
    )
    hero = Hero(id=HeroID("h1"), name="H1", deck=[card], hand=[card], team=TeamColor.RED)
    # Ensure initialized
    card.state = CardState.HAND 
    
    t = Team(color=TeamColor.RED, heroes=[hero])
    state = GameState(board=b, teams={TeamColor.RED: t})
    state.unit_locations[HeroID("h1")] = Hex(q=0,r=0,s=0)
    
    return state, hero, card

def test_card_state_lifecycle(state_wrapper):
    state, hero, card = state_wrapper
    
    # 1. Start: UNRESOLVED
    # Play Card
    state.phase = GamePhase.PLANNING
    PlayCardCommand(hero.id, card.id).execute(state)
    assert card.state == CardState.UNRESOLVED
    
    # Reveal
    from goa2.engine.actions import RevealCardsCommand
    RevealCardsCommand().execute(state) # Moves to ResolutionQueue
    assert card.state == CardState.UNRESOLVED
    
    # Resolve Next (Starts Turn)
    ResolveNextCommand().execute(state)
    assert card.state == CardState.UNRESOLVED
    
    # Choose Action (Movement)
    ChooseActionCommand(ActionType.MOVEMENT).execute(state)
    assert card.state == CardState.UNRESOLVED
    
    # Perform Movement (Finishes Turn)
    # Move to neighbor
    target = Hex(q=1, r=-1, s=0)
    PerformMovementCommand(target).execute(state) 
    
    # End: RESOLVED
    assert card.state == CardState.RESOLVED

def test_defense_card_state(state_wrapper):
    state, hero, card = state_wrapper
    
    # Setup Attacker
    attacker = Hero(id=HeroID("mock_enemy"), name="Enemy", deck=[], team=TeamColor.BLUE)
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, heroes=[attacker])
    state.unit_locations[attacker.id] = Hex(q=1, r=1, s=-2) # somewhere

    # Setup: Hero needs another card for defense
    def_card = Card(
        id="d1", name="Def", tier=CardTier.I, color=CardColor.BLUE, initiative=1,
        primary_action=ActionType.DEFENSE, primary_action_value=3,
        effect_id="", effect_text="", state=CardState.HAND
    )
    hero.hand.append(def_card)
    
    # Mock specific request context
    from goa2.domain.input import InputRequest, InputRequestType
    req = InputRequest(
        id="req1", 
        player_id=hero.id, 
        request_type=InputRequestType.DEFENSE_CARD,
        context={"attacker_id": "mock_enemy"}
    )
    state.input_stack.append(req)
    
    # Needed for command execution (resolution queue peek)
    # Mock an attacker in queue with some card
    att_card = Card(id="att_c", name="Att", tier=CardTier.I, primary_action=ActionType.ATTACK, color=CardColor.RED, initiative=5, effect_id="", effect_text="")
    state.resolution_queue = [("mock_enemy", att_card)] 
    
    # Execute Defense
    PlayDefenseCommand(def_card.id).execute(state)
    
    assert def_card.state == CardState.DISCARD

def test_hold_action_state(state_wrapper):
    state, hero, card = state_wrapper
    
    # Setup
    state.phase = GamePhase.PLANNING
    PlayCardCommand(hero.id, card.id).execute(state)
    from goa2.engine.actions import RevealCardsCommand
    RevealCardsCommand().execute(state)
    ResolveNextCommand().execute(state)
    
    # Choose HOLD
    ChooseActionCommand(ActionType.HOLD).execute(state)
    
    assert card.state == CardState.RESOLVED
