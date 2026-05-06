from __future__ import annotations

from typing import Any

from goa2.domain.models import FilterType
from goa2.domain.models.enums import (
    ActionType,
    CardColor,
    CardContainerType,
)
from goa2.domain.state import GameState

# -----------------------------------------------------------------------------
# Base Filter
# -----------------------------------------------------------------------------
from goa2.engine.filters_base import FilterCondition


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

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False
        hero = state.get_hero(candidate)
        if not hero:
            return False
        if self.container == CardContainerType.HAND:
            count = len(hero.hand)
        elif self.container == CardContainerType.DISCARD:
            count = len(hero.discard_pile)
        elif self.container == CardContainerType.PLAYED:
            count = len([c for c in hero.played_cards if c is not None])
        elif self.container == CardContainerType.DECK:
            count = len(hero.deck)
        else:
            return False
        if self.min_cards is not None and count < self.min_cards:
            return False
        if self.max_cards is not None and count > self.max_cards:
            return False
        return True


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
        hero = state.get_hero(str(candidate))
        if not hero:
            return False

        actor = state.get_hero(state.current_actor_id)
        if not actor:
            return False
        current_turn_index = actor.resolved_turn_count

        cards_to_check = []

        # Card from current turn if already resolved
        if current_turn_index < len(hero.played_cards):
            card = hero.played_cards[current_turn_index]
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
