import pytest
from goa2.domain.state import GameState
from goa2.engine.phases import GamePhase
from goa2.domain.models import TeamColor, Team, Hero, Card, CardTier, CardColor, ActionType, CardState
from goa2.domain.types import HeroID, CardID
from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ChooseActionCommand
from goa2.domain.board import Board

@pytest.fixture
def state_with_hero():
    card = Card(
        id=CardID("c1"),
        name="Test Card",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=10,
        primary_action=ActionType.HOLD, # Simple action
        effect_id="test_effect",
        effect_text="Test",
        state=CardState.HAND
    )
    
    hero = Hero(
        id=HeroID("h1"),
        name="Hero",
        deck=[],
        hand=[card]
    )
    
    state = GameState(
        board=Board(),
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero])},
        phase=GamePhase.PLANNING
    )
    return state, hero, card

def test_card_lifecycle(state_with_hero):
    state, hero, card = state_with_hero
    
    # 1. Initial State
    assert card.state == CardState.HAND
    assert card.is_facedown is True # Default is Hidden
    assert card.tier == CardTier.UNTIERED # Masked
    
    # 2. Play Card
    cmd = PlayCardCommand(hero_id=hero.id, card_id=card.id)
    state = cmd.execute(state)
    
    # Assert PLAYED state
    assert card.state == CardState.PLAYED
    assert card.is_facedown is True # Still Hidden!
    assert card.tier == CardTier.UNTIERED # Still Masked
    
    # 3. Reveal Cards
    reveal_cmd = RevealCardsCommand()
    state = reveal_cmd.execute(state)
    
    # Assert UNRESOLVED state (Transitioned by Reveal)
    assert card.state == CardState.UNRESOLVED
    assert card.is_facedown is False # Revealed!
    assert card.tier == CardTier.UNTIERED # Wait, fixture made it UNTIERED.
    assert card.real_tier == CardTier.UNTIERED

def test_facedown_default():
    c = Card(
        id=CardID("fd"),
        name="FD",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        effect_id="x",
        effect_text="x"
    )
    assert c.is_facedown is True
    # Masked values
    assert c.tier == CardTier.UNTIERED 
    assert c.color is None
    # Real values
    assert c.real_tier == CardTier.I
