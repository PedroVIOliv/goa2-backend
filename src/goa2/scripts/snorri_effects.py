"""Snorri — rune hero card effects.

Core mechanic: ``inscribe_the_runes`` places 4 rune markers (one per turn
slot) via ``PlaceRunesStep`` (see ``engine/steps/markers.py``). A rune is
*active* while it sits below the slot matching ``state.turn``. Every other
Snorri card keys off :func:`active_runes`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from goa2.domain.models import Card, RuneType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import GameStep, PlaceRunesStep

if TYPE_CHECKING:
    from goa2.domain.models import Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


def _find_card_owner(state: GameState, card: Card) -> Hero | None:
    """Locate the hero who owns ``card`` — scans every card container,
    including ``ultimate_card``, on every hero (both teams).

    Deliberately NOT ``state.current_actor_id``: a copied Snorri card
    (e.g. NebKher's Mind Grip) is performed by another hero but must still
    see Snorri's runes (TDD §19).
    """
    for team in state.teams.values():
        for hero in team.heroes:
            if hero.current_turn_card is not None and hero.current_turn_card.id == card.id:
                return hero
            if hero.extra_turn_card is not None and hero.extra_turn_card.id == card.id:
                return hero
            for container in (hero.hand, hero.deck, hero.discard_pile, hero.played_cards):
                if any(c is not None and c.id == card.id for c in container):
                    return hero
            if hero.ultimate_card is not None and hero.ultimate_card.id == card.id:
                return hero
    return None


def active_runes(state: GameState, card: Card, context: dict[str, Any]) -> set[RuneType]:
    """The set of currently-active runes for ``card``.

    Base activity: the rune below the turn slot matching ``state.turn``,
    read from the CARD OWNER's ``rune_slots`` (not the current actor — see
    :func:`_find_card_owner`). Unioned with any rune named by
    ``context["snorri_ult_rune_action"]`` / ``context["snorri_ult_rune_defense"]``
    (Rune Mastery ultimate, wired up in a later task) — read defensively
    since most callers never set them.
    """
    active: set[RuneType] = set()

    owner = _find_card_owner(state, card)
    if owner is not None:
        turn_rune = owner.rune_slots.get(state.turn)
        if turn_rune is not None:
            active.add(RuneType(turn_rune))

    for key in ("snorri_ult_rune_action", "snorri_ult_rune_defense"):
        raw = context.get(key)
        if raw:
            active.add(RuneType(raw))

    return active


@register_effect("inscribe_the_runes")
class InscribeTheRunesEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        return [PlaceRunesStep(hero_id=hero.id)]
