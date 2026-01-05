import pytest
from goa2.domain.models import Hero, Card, CardTier, CardColor, ActionType, CardState
from goa2.domain.types import HeroID

@pytest.fixture
def cards():
    return [
        Card(id=f"c{i}", name=f"Card {i}", tier=CardTier.I, color=CardColor.RED, initiative=10+i, primary_action=ActionType.ATTACK, primary_action_value=2, effect_id=f"e{i}", effect_text="text")
        for i in range(5)
    ]

@pytest.fixture
def hero(cards):
    # Set initial states to HAND for those we will put in hand
    for c in cards[:4]:
        c.state = CardState.HAND
        c.is_facedown = False
        
    h = Hero(
        id=HeroID("hero_1"),
        name="Test Hero",
        deck=cards,
        hand=[cards[0], cards[1], cards[2], cards[3]], 
        discard_pile=[],
        played_cards=[]
    )
    # c2 will be discarded
    h.discard_card(cards[2], from_hand=True)
    # c3 will be current turn card (Unresolved)
    h.play_card(cards[3]) 
    return h

def test_swap_hand_and_unresolved(hero, cards):
    # c0 (Hand) vs c3 (Unresolved)
    card_hand = cards[0]
    card_unres = cards[3]
    
    hero.swap_cards(card_hand, card_unres)
    
    # Verify Locations
    assert card_unres in hero.hand
    assert hero.current_turn_card == card_hand
    
    # Verify State attributes
    assert card_hand.state == CardState.UNRESOLVED
    assert card_hand.is_facedown == True
    
    assert card_unres.state == CardState.HAND
    assert card_unres.is_facedown == False

def test_swap_hand_and_resolved(hero, cards):
    # Setup: Resolve c3 first, then swap with c0
    hero.resolve_current_card()
    card_hand = cards[0]
    card_res = cards[3]
    
    assert card_res in hero.played_cards
    
    hero.swap_cards(card_hand, card_res)
    
    # Verify Locations
    assert card_res in hero.hand
    assert card_hand in hero.played_cards
    
    # Verify State attributes
    assert card_hand.state == CardState.RESOLVED
    assert card_res.state == CardState.HAND

def test_swap_unresolved_and_resolved(hero, cards):
    # Setup: c3 is Unresolved. Let's make c4 Resolved manually.
    card_unres = cards[3]
    card_res = cards[4]
    
    card_res.state = CardState.RESOLVED
    hero.played_cards.append(card_res)
    
    hero.swap_cards(card_unres, card_res)
    
    # Verify Locations
    assert hero.current_turn_card == card_res
    assert card_unres in hero.played_cards
    
    # Verify States
    assert card_res.state == CardState.UNRESOLVED
    assert card_unres.state == CardState.RESOLVED

def test_swap_hand_and_discard(hero, cards):
    card_hand = cards[0]
    card_disc = cards[2]
    
    hero.swap_cards(card_hand, card_disc)
    
    assert card_disc in hero.hand
    assert card_hand in hero.discard_pile
    
    assert card_disc.state == CardState.HAND
    assert card_hand.state == CardState.DISCARD
    assert card_hand.is_facedown == False

def test_swap_within_same_list(hero, cards):
    # c0 and c1 are both in hand
    c0 = cards[0]
    c1 = cards[1]
    
    # Original order
    assert hero.hand == [c0, c1]
    
    hero.swap_cards(c0, c1)
    
    # Order should be swapped
    assert hero.hand == [c1, c0]

def test_swap_invalid_card(hero, cards):
    external_card = Card(id="ext", name="Ext", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, primary_action_value=2, effect_id="e", effect_text="t")
    
    with pytest.raises(ValueError, match="not found"):
        hero.swap_cards(cards[0], external_card)
