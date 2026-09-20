from __future__ import annotations

from typing import Any

from goa2.domain.models import FilterType
from goa2.domain.models.enums import (
    ActionType,
    CardColor,
    CardContainerType,
    CardState,
)
from goa2.domain.state import GameState
from goa2.domain.types import HeroID

# -----------------------------------------------------------------------------
# Base Filter
# -----------------------------------------------------------------------------
from goa2.engine.filters_base import FilterCondition


class HasUnresolvedCardFilter(FilterCondition):
    """Passes hero candidates whose current_turn_card is revealed and still
    UNRESOLVED (i.e. they have "an unresolved card"). Used by Hanu's Hurry Up!."""

    type: FilterType = FilterType.HAS_UNRESOLVED_CARD

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False
        hero = state.get_hero(HeroID(candidate))
        if not hero:
            return False
        card = hero.current_turn_card
        return card is not None and card.state == CardState.UNRESOLVED


class HasResolvedCardFilter(FilterCondition):
    """Passes hero candidates who have already resolved a card THIS TURN.

    A hero resolved this turn iff their slot for the game turn is filled,
    or their current_turn_card is
    RESOLVED but not yet finalized (own-turn / action-control windows).
    Used by Emmitt's Time Loop / Time Warp / Time Snare / Time Trap /
    Time Bomb ("who has already resolved a card this turn")."""

    type: FilterType = FilterType.HAS_RESOLVED_CARD

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False
        hero = state.get_hero(HeroID(candidate))
        if not hero:
            return False
        card = hero.current_turn_card
        if card is not None and card.state == CardState.RESOLVED:
            return True
        return hero.card_in_turn_slot(state.turn) is not None


class HasPreviousSlotCardFilter(FilterCondition):
    """Passes hero candidates with a card in their PREVIOUS turn slot.

    Turn indexing follows the game turn, independent of whether either hero
    has already acted or removed their current card. On the first turn there is
    no previous slot and nothing passes. Used by NebKher's Mind Grip
    ("the card in the previous turn slot of an enemy hero")."""

    type: FilterType = FilterType.HAS_PREVIOUS_SLOT_CARD

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False
        hero = state.get_hero(HeroID(candidate))
        if not hero:
            return False
        return hero.card_in_turn_slot(state.turn - 1) is not None


class CardsInContainerFilter(FilterCondition):
    """
    Filters unit candidates to heroes with a card count in a given container
    that satisfies min_cards and/or max_cards bounds.
    Non-hero candidates are rejected.
    """

    type: FilterType = FilterType.CARDS_IN_CONTAINER
    container: CardContainerType = CardContainerType.HAND
    min_cards: int | None = None
    max_cards: int | None = None
    # Facedown cards outside the hand have no readable identity (rulebook), so
    # effects that need to READ a card there (Takahide's color source) must not
    # count them.
    exclude_facedown: bool = False

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False
        hero = state.get_hero(HeroID(candidate))
        if not hero:
            return False
        if self.container == CardContainerType.HAND:
            cards = list(hero.hand)
        elif self.container == CardContainerType.DISCARD:
            cards = list(hero.discard_pile)
        elif self.container == CardContainerType.PLAYED:
            cards = [c for c in hero.played_cards if c is not None]
        elif self.container == CardContainerType.DECK:
            cards = list(hero.deck)
        else:
            return False
        if self.exclude_facedown:
            cards = [c for c in cards if not c.is_facedown]
        count = len(cards)
        if self.min_cards is not None and count < self.min_cards:
            return False
        return not (self.max_cards is not None and count > self.max_cards)


class PlayedCardFilter(FilterCondition):
    """
    Checks if a candidate hero played a card matching criteria in the current turn.

    Uses masked properties (current_primary_action, current_color) so facedown
    cards naturally don't match.
    """

    type: FilterType = FilterType.PLAYED_CARD
    action_type: ActionType | None = None
    card_color: CardColor | None = None

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        hero = state.get_hero(HeroID(str(candidate)))
        if not hero:
            return False

        cards_to_check = []

        # Card from current turn if already resolved
        card = hero.card_in_turn_slot(state.turn)
        if card:
            cards_to_check.append(card)

        # Card from current turn if not yet resolved (respects facedown)
        if hero.current_turn_card:
            cards_to_check.append(hero.current_turn_card)

        for card in cards_to_check:
            if self.action_type and card.current_primary_action != self.action_type:
                continue
            if self.card_color and card.current_color != self.card_color:
                continue
            return True
        return False
