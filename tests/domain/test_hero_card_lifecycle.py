import pytest
from goa2.domain.models import Hero, Card, CardTier, CardColor, ActionType, CardState, Team, TeamColor
from goa2.domain.types import HeroID
from goa2.engine.steps import FinalizeHeroTurnStep
from goa2.domain.state import GameState
from goa2.domain.board import Board

@pytest.fixture
def sample_card():
    return Card(
        id="c1", 
        name="Test Card", 
        tier=CardTier.I, 
        color=CardColor.RED, 
        initiative=10, 
        primary_action=ActionType.ATTACK, 
        primary_action_value=2,
        effect_id="e1", 
        effect_text="text"
    )

@pytest.fixture
def hero(sample_card):
    h = Hero(
        id=HeroID("hero_1"),
        name="Test Hero",
        deck=[sample_card],
        hand=[sample_card]
    )
    return h

def test_play_card_lifecycle(hero, sample_card):
    # 1. Start in Hand
    assert sample_card in hero.hand
    assert hero.current_turn_card is None
    assert len(hero.played_cards) == 0
    
    # 2. Play Card
    hero.play_card(sample_card)
    
    # Verify: Removed from Hand
    assert sample_card not in hero.hand
    
    # Verify: Set as Current Turn Card (Unresolved)
    assert hero.current_turn_card == sample_card
    assert sample_card.state == CardState.UNRESOLVED
    assert sample_card.is_facedown == True
    assert sample_card.played_this_round == True
    
    # Verify: Not yet in Resolved list
    assert len(hero.played_cards) == 0

def test_resolve_card_lifecycle(hero, sample_card):
    # Setup: Play first
    hero.play_card(sample_card)
    
    # 3. Resolve Card
    hero.resolve_current_card()
    
    # Verify: Moved to Resolved List
    assert hero.current_turn_card is None
    assert sample_card in hero.played_cards
    assert sample_card.state == CardState.RESOLVED
    # Note: is_facedown logic handles masking, but resolving doesn't inherently flip it up
    # (Revelation phase usually flips it). 
    
def test_discard_from_hand(hero, sample_card):
    hero.discard_card(sample_card, from_hand=True)
    
    assert sample_card not in hero.hand
    assert sample_card in hero.discard_pile
    assert sample_card.state == CardState.DISCARD
    assert sample_card.is_facedown == False

def test_discard_from_resolved(hero, sample_card):
    # Setup: Play and Resolve
    hero.play_card(sample_card)
    hero.resolve_current_card()
    
    assert sample_card in hero.played_cards
    
    # Discard (Force from_hand=False)
    hero.discard_card(sample_card, from_hand=False)
    
    assert sample_card not in hero.played_cards
    assert sample_card in hero.discard_pile
    assert sample_card.state == CardState.DISCARD

def test_discard_from_unresolved(hero, sample_card):
    # Setup: Play but don't resolve
    hero.play_card(sample_card)
    assert hero.current_turn_card == sample_card
    
    # Discard (e.g. Death Penalty nullify?)
    hero.discard_card(sample_card, from_hand=False)
    
    assert hero.current_turn_card is None
    assert sample_card in hero.discard_pile

def test_retrieve_cards_full_reset(hero, sample_card):
    # Setup: 
    # c1: Resolved
    # c2: Unresolved (if we had 2 cards)
    # c3: Discarded
    
    c2 = Card(id="c2", name="C2", tier=CardTier.I, color=CardColor.BLUE, initiative=5, primary_action=ActionType.DEFENSE, primary_action_value=2, effect_id="e", effect_text="t")
    c3 = Card(id="c3", name="C3", tier=CardTier.I, color=CardColor.GREEN, initiative=5, primary_action=ActionType.SKILL, primary_action_value=None, effect_id="e", effect_text="t")
    
    hero.hand.extend([c2, c3])
    
    hero.play_card(sample_card)
    hero.resolve_current_card() # c1 -> Resolved
    
    hero.play_card(c2) # c2 -> Unresolved
    
    hero.discard_card(c3, from_hand=True) # c3 -> Discard
    
    # Pre-check
    assert sample_card in hero.played_cards
    assert hero.current_turn_card == c2
    assert c3 in hero.discard_pile
    
    # Execute Retrieve
    hero.retrieve_cards()
    
    # Verify All in Hand
    assert sample_card in hero.hand
    assert c2 in hero.hand
    assert c3 in hero.hand
    
    # Verify States Reset
    for c in [sample_card, c2, c3]:
        assert c.state == CardState.HAND
        assert c.is_facedown == False
        assert c.played_this_round == False
        
    # Verify Containers Empty
    assert len(hero.played_cards) == 0
    assert len(hero.discard_pile) == 0
    assert hero.current_turn_card is None

def test_finalize_turn_step_integration(hero, sample_card):
    # Setup Engine Context
    state = GameState(board=Board(), teams={})
    # Mock finding hero
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[hero], minions=[])
    
    # Setup Hero State
    hero.play_card(sample_card)
    assert hero.current_turn_card == sample_card
    
    # Run Step
    step = FinalizeHeroTurnStep(hero_id=hero.id)
    step.resolve(state, {})
    
    # Verify Effect
    assert hero.current_turn_card is None
    assert sample_card in hero.played_cards