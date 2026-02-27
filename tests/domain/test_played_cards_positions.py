"""
Test fixed-position played_cards feature.
"""

import pytest
from goa2.domain.models import (
    Card,
    Hero,
    TeamColor,
    CardTier,
    CardColor,
    ActionType,
    CardState,
)
from goa2.domain.types import HeroID


@pytest.fixture
def hero():
    """Create a simple hero for testing."""
    cards = [
        Card(
            id=f"card_{i}",
            name=f"Card {i}",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=i,
            primary_action=ActionType.ATTACK,
            primary_action_value=i,
            secondary_actions={ActionType.DEFENSE: i, ActionType.MOVEMENT: i},
            effect_id=f"effect_{i}",
            effect_text=f"Effect {i}",
        )
        for i in range(1, 6)
    ]
    hero = Hero(
        id=HeroID("hero_test"),
        name="Test Hero",
        deck=cards,
        hand=cards[:],
    )
    return hero


def test_played_cards_fixed_positions(hero):
    """Test that cards go to fixed positions based on turn."""
    # Turn 1: card_1 goes to position 0
    card1 = hero.hand[0]
    hero.play_card(card1)
    hero.resolve_current_card()

    assert len(hero.played_cards) == 1
    assert hero.played_cards[0] == card1
    assert hero.resolved_turn_count == 1

    # Turn 2: card_2 goes to position 1
    card2 = hero.hand[0]
    hero.play_card(card2)
    hero.resolve_current_card()

    assert len(hero.played_cards) == 2
    assert hero.played_cards[0] == card1
    assert hero.played_cards[1] == card2
    assert hero.resolved_turn_count == 2

    # Turn 3: card_3 goes to position 2
    card3 = hero.hand[0]
    hero.play_card(card3)
    hero.resolve_current_card()

    assert len(hero.played_cards) == 3
    assert hero.played_cards[0] == card1
    assert hero.played_cards[1] == card2
    assert hero.played_cards[2] == card3
    assert hero.resolved_turn_count == 3


def test_played_cards_removal_preserves_positions(hero):
    """Test that removing a card leaves a None placeholder."""
    # Play and resolve 3 cards
    for _ in range(3):
        card = hero.hand[0]
        hero.play_card(card)
        hero.resolve_current_card()

    card1, card2, card3 = hero.played_cards

    # Remove card2 (turn 2 card)
    hero.discard_card(card2, from_hand=False)

    # Position 1 should be None, others unchanged
    assert hero.played_cards[0] == card1
    assert hero.played_cards[1] is None
    assert hero.played_cards[2] == card3
    assert len(hero.played_cards) == 3

    # Turn 4 card should go to position 3, not fill the gap
    card4 = hero.hand[0]
    hero.play_card(card4)
    hero.resolve_current_card()

    assert hero.played_cards[0] == card1
    assert hero.played_cards[1] is None
    assert hero.played_cards[2] == card3
    assert hero.played_cards[3] == card4
    assert len(hero.played_cards) == 4


def test_return_card_to_hand_preserves_positions(hero):
    """Test that returning a card to hand leaves a None placeholder."""
    # Play and resolve 3 cards
    for _ in range(3):
        card = hero.hand[0]
        hero.play_card(card)
        hero.resolve_current_card()

    card1, card2, card3 = hero.played_cards

    # Return card1 to hand
    hero.return_card_to_hand(card1)

    # Position 0 should be None, others unchanged
    assert hero.played_cards[0] is None
    assert hero.played_cards[1] == card2
    assert hero.played_cards[2] == card3

    # Card should be in hand
    assert card1 in hero.hand
    assert card1.state == CardState.HAND


def test_retrieve_cards_clears_played_cards(hero):
    """Test that end of round clears played_cards and resets counter."""
    # Play and resolve 3 cards
    for _ in range(3):
        card = hero.hand[0]
        hero.play_card(card)
        hero.resolve_current_card()

    assert hero.resolved_turn_count == 3
    assert len(hero.played_cards) == 3

    # End of round: retrieve cards
    hero.retrieve_cards()

    # played_cards should be cleared, counter reset
    assert len(hero.played_cards) == 0
    assert hero.resolved_turn_count == 0

    # All cards should be in hand
    assert len(hero.hand) == 5  # Original 5 cards


def test_swap_cards_with_none_placeholders(hero):
    """Test that swap_cards works with None placeholders."""
    # Play and resolve 3 cards
    for _ in range(3):
        card = hero.hand[0]
        hero.play_card(card)
        hero.resolve_current_card()

    card1, card2, card3 = hero.played_cards

    # Remove card2 (turn 2 card) leaving None at position 1
    hero.discard_card(card2, from_hand=False)
    assert hero.played_cards[1] is None

    # Swap card1 with card3
    hero.swap_cards(card1, card3)

    # Positions should be swapped, None unchanged
    assert hero.played_cards[0] == card3
    assert hero.played_cards[1] is None
    assert hero.played_cards[2] == card1


def test_discard_card_from_played_sets_none(hero):
    """Test that discarding a card from played_cards sets position to None."""
    # Play and resolve card
    card1 = hero.hand[0]
    hero.play_card(card1)
    hero.resolve_current_card()

    # Discard card
    hero.discard_card(card1, from_hand=False)

    # Position should be None
    assert hero.played_cards[0] is None

    # Card should be in discard pile
    assert card1 in hero.discard_pile
    assert card1.state == CardState.DISCARD


def test_round_transition_resets_positions(hero):
    """Test that new round starts cards from position 0 again."""
    # ROUND 1: Play and resolve 3 cards
    round1_cards = []
    for _ in range(3):
        card = hero.hand[0]
        hero.play_card(card)
        hero.resolve_current_card()
        round1_cards.append(card)

    assert hero.resolved_turn_count == 3
    assert hero.played_cards[0] == round1_cards[0]
    assert hero.played_cards[1] == round1_cards[1]
    assert hero.played_cards[2] == round1_cards[2]

    # End of round 1
    hero.retrieve_cards()
    assert len(hero.played_cards) == 0
    assert hero.resolved_turn_count == 0

    # ROUND 2: Play new cards - should go to position 0, 1, 2 again
    round2_cards = []
    for _ in range(3):
        card = hero.hand[0]
        hero.play_card(card)
        hero.resolve_current_card()
        round2_cards.append(card)

    assert hero.resolved_turn_count == 3
    assert len(hero.played_cards) == 3
    # Cards should be at positions 0, 1, 2 (not 3, 4, 5)
    assert hero.played_cards[0] == round2_cards[0]
    assert hero.played_cards[1] == round2_cards[1]
    assert hero.played_cards[2] == round2_cards[2]
