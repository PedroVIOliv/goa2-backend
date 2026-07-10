"""Snorri — rune hero card effects.

Core mechanic: ``inscribe_the_runes`` places 4 rune markers (one per turn
slot) via ``PlaceRunesStep`` (see ``engine/steps/markers.py``). A rune is
*active* while it sits below the slot matching ``state.turn``. Every other
Snorri card keys off :func:`active_runes`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from goa2.domain.models import (
    AffectsFilter,
    Card,
    DurationType,
    EffectScope,
    EffectType,
    RuneType,
    Shape,
)
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    ChooseRuneStep,
    CreateEffectStep,
    GameStep,
    PlaceRunesStep,
    SetContextFlagStep,
)

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


class OathEffect(CardEffect):
    """Shared rune-gated defense implementation for Snorri's Oath cards."""

    rune_blocks: ClassVar[dict[RuneType, str]] = {}
    choose_one: ClassVar[bool] = False
    _choice_key: ClassVar[str] = "snorri_oath_rune"
    _matches_key: ClassVar[str] = "snorri_oath_rune_matches"

    @staticmethod
    def _blocks(block_type: str, context: dict[str, Any]) -> bool:
        return {
            "basic": bool(context.get("attack_is_basic")),
            "melee": not bool(context.get("attack_is_ranged")),
            "ranged": bool(context.get("attack_is_ranged")),
            "non_basic": not bool(context.get("attack_is_basic")),
        }[block_type]

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: dict[str, Any],
    ) -> list[GameStep]:
        active = [rune for rune in RuneType if rune in active_runes(state, card, context)]
        eligible = [rune for rune in active if rune in self.rune_blocks]
        matching = [rune for rune in eligible if self._blocks(self.rune_blocks[rune], context)]

        # Reset both combat flags explicitly: an attack context must never
        # inherit a prior defense result.
        steps: list[GameStep] = [
            SetContextFlagStep(key="auto_block", value=False),
            SetContextFlagStep(key="defense_invalid", value=True),
        ]

        if not eligible:
            return steps

        if not self.choose_one or len(eligible) == 1:
            if matching:
                steps.extend(
                    [
                        SetContextFlagStep(key="auto_block", value=True),
                        SetContextFlagStep(key="defense_invalid", value=False),
                    ]
                )
            return steps

        steps.extend(
            [
                ChooseRuneStep(
                    output_key=self._choice_key,
                    options=eligible,
                    prompt="Choose one active rune",
                    matching_options=matching,
                    matches_output_key=self._matches_key,
                ),
                SetContextFlagStep(key="auto_block", value=True, active_if_key=self._matches_key),
                SetContextFlagStep(
                    key="defense_invalid", value=False, active_if_key=self._matches_key
                ),
            ]
        )
        return steps

    def build_on_block_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: dict[str, Any],
    ) -> list[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
                scope=EffectScope(
                    shape=Shape.POINT, origin_id=defender.id, affects=AffectsFilter.SELF
                ),
                duration=DurationType.THIS_TURN,
                is_active=True,
                use_context_card=False,
            )
        ]


@register_effect("oath_of_endurance")
class OathOfEnduranceEffect(OathEffect):
    rune_blocks: ClassVar[dict[RuneType, str]] = {
        RuneType.HORN: "basic",
        RuneType.AXE: "melee",
    }


@register_effect("oath_of_fortitude")
class OathOfFortitudeEffect(OathOfEnduranceEffect):
    rune_blocks: ClassVar[dict[RuneType, str]] = {
        **OathOfEnduranceEffect.rune_blocks,
        RuneType.BIRD: "ranged",
    }


@register_effect("oath_of_perseverance")
class OathOfPerseveranceEffect(OathOfFortitudeEffect):
    rune_blocks: ClassVar[dict[RuneType, str]] = {
        **OathOfFortitudeEffect.rune_blocks,
        RuneType.ANVIL: "non_basic",
    }
    choose_one: ClassVar[bool] = True
