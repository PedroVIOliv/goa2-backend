import pytest
from goa2.domain.models import Hero, Card, CardTier, CardColor, ActionType, CardState
from goa2.domain.types import HeroID

@pytest.fixture
def sample_card():
    return Card(
        id="c1", 
        name="Test Card", 
        tier=CardTier.I, 
        color=CardColor.RED, 
        initiative=10, 
        primary_action=ActionType.ATTACK, 
        effect_id="e1", 
        effect_text="text"
    )

@pytest.fixture
def hero(sample_card):
    return Hero(
        id=HeroID("hero_1"),
        name="Test Hero",
        deck=[sample_card],
        hand=[sample_card]
    )

def test_mid_turn_retrieval_unresolved(hero, sample_card):
    """
    Test checking implications of retrieving a card while it is 'current_turn_card'
    (Played but not yet Resolved/Acted upon).
    """
    # 1. Play Card
    hero.play_card(sample_card)
    assert hero.current_turn_card == sample_card
    assert sample_card.played_this_round
    
    # 2. Simulate Effect: Retrieve Card
    hero.return_card_to_hand(sample_card)
    
    # 3. Verify State
    assert hero.current_turn_card is None
    assert sample_card in hero.hand
    assert sample_card.state == CardState.HAND
    assert not sample_card.is_facedown
    
    # 4. Verify Lifecycle Flag Persists
    # This is the crucial check: The card WAS played this round, even if returned.
    assert sample_card.played_this_round
    
    # 5. Verify Initiative Impact
    # If the card is gone, initiative drops to 0 (default/base)
    assert hero.get_effective_initiative() == 0

def test_mid_turn_retrieval_resolved(hero, sample_card):
    """
    Test retrieving a card after it has been resolved (moved to played_cards).
    """
    hero.play_card(sample_card)
    hero.resolve_current_card()
    
    assert sample_card in hero.played_cards
    
    hero.return_card_to_hand(sample_card)
    
    assert sample_card not in hero.played_cards
    assert sample_card in hero.hand
    assert sample_card.played_this_round
