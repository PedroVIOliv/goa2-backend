"""Shared scenario helpers for Takahide effect tests."""

from __future__ import annotations

from collections.abc import Sequence

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import Card, CardState, Hero
from goa2.domain.state import GameState
from tests.engine.effects.builders import Coords, EffectScenarioBuilder

TAKAHIDE = "hero_takahide"


def _fresh_takahide() -> Hero:
    hero = HeroRegistry.get("Takahide")
    assert hero is not None, "Takahide is not registered"
    hero.initialize_state()
    return hero


def takahide_card(card_id: str) -> Card:
    """A deep copy of one of Takahide's cards (deck or ultimate)."""
    hero = HeroRegistry.get("Takahide")
    assert hero is not None
    cards = list(hero.deck) + ([hero.ultimate_card] if hero.ultimate_card else [])
    for card in cards:
        if card.id == card_id:
            return card.model_copy(deep=True)
    raise LookupError(card_id)


def takahide_state(
    card_id: str,
    *,
    allies: Sequence[Coords] = (),
    enemies: Sequence[Coords] = ((3, 0, -3),),
    hexes: Sequence[Coords] | None = None,
    at: Coords = (0, 0, 0),
) -> GameState:
    """Takahide (RED) at origin, resolving `card_id`, in a small arena.

    Takahide carries his real deck (master list) with `card_id` committed as the
    faceup UNRESOLVED turn card, so gold-cycle tests can inspect deck state.
    Allies are `hero_ally_1..`, enemies `hero_enemy_1..`; both start with empty
    decks — tests that need cards set `hand`/`discard_pile` directly.
    """
    builder = EffectScenarioBuilder()
    builder = builder.small_arena() if hexes is None else builder.with_hexes(hexes)
    builder = builder.red_hero(TAKAHIDE, at=at)
    for i, coords in enumerate(allies, 1):
        builder = builder.red_hero(f"hero_ally_{i}", at=coords)
    for i, coords in enumerate(enemies, 1):
        builder = builder.blue_hero(f"hero_enemy_{i}", at=coords)

    state = builder.with_actor(TAKAHIDE).build()
    equip_takahide(state, card_id)
    return state


def equip_takahide(state: GameState, card_id: str) -> Card:
    """Give the state's Takahide his real deck and commit `card_id` as turn card."""
    fresh = _fresh_takahide()
    taka = state.get_hero(TAKAHIDE)
    assert taka is not None

    card = next(c for c in fresh.deck if c.id == card_id)
    if card in fresh.hand:
        fresh.hand.remove(card)
    card.state = CardState.UNRESOLVED
    card.is_facedown = False
    card.played_this_round = True

    taka.deck = fresh.deck
    taka.hand = fresh.hand
    taka.items = fresh.items
    taka.ultimate_card = fresh.ultimate_card
    taka.current_turn_card = card
    return card


def deck_card(hero: Hero, card_id: str) -> Card:
    """The Card object with `card_id` in the hero's master deck list."""
    return next(c for c in hero.deck if c.id == card_id)
