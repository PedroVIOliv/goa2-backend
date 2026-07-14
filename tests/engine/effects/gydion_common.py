"""Shared fresh-card helpers for Gydion effect tests."""

from __future__ import annotations

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import Card, Hero, SpellCard


def fresh_gydion() -> Hero:
    hero = HeroRegistry.get("Gydion")
    assert hero is not None, "Gydion is not registered"
    hero.initialize_state()
    return hero


def gydion_card(card_id: str) -> Card:
    hero = HeroRegistry.get("Gydion")
    assert hero is not None
    cards = [*hero.deck]
    if hero.ultimate_card is not None:
        cards.append(hero.ultimate_card)
    return next(card.model_copy(deep=True) for card in cards if card.id == card_id)


def gydion_spell(spell_id: str) -> SpellCard:
    hero = HeroRegistry.get("Gydion")
    assert hero is not None
    return next(spell.model_copy(deep=True) for spell in hero.spells if spell.id == spell_id)
