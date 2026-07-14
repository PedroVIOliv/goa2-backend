"""Gydion card and spell effects."""

from __future__ import annotations

from typing import ClassVar

from goa2.domain.models import Card, Hero
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffect, CardEffectRegistry, register_effect
from goa2.engine.stats import CardStats
from goa2.engine.steps import CastSpellStep, GameStep, PrepareSpellbookStep

SPELL_ACCESS_MAP: dict[str, tuple[str, ...]] = {
    "cantrip": ("shocking_grasp", "magic_missile", "expeditious_retreat"),
    "elementary_evocation": ("burning_hands",),
    "lesser_evocation": ("burning_hands", "fireball"),
    "greater_evocation": ("burning_hands", "fireball", "sunburst"),
    "elementary_abjuration": ("shield",),
    "lesser_abjuration": ("shield", "banishment"),
    "greater_abjuration": ("shield", "banishment", "invulnerability"),
    "elementary_enchantment": ("suggestion",),
    "lesser_enchantment": ("suggestion", "dominate_person"),
    "greater_enchantment": ("suggestion", "dominate_person", "power_word_kill"),
    "lesser_necromancy": ("vampiric_touch", "create_undead"),
    "greater_necromancy": ("vampiric_touch", "create_undead", "energy_drain"),
    "lesser_conjuration": ("find_familiar", "dimension_door"),
    "greater_conjuration": ("find_familiar", "dimension_door", "cloud_kill"),
    "lesser_transmutation": ("midas_touch", "disintegrate"),
    "greater_transmutation": ("midas_touch", "disintegrate", "polymorph"),
}


@register_effect("prepare_spells")
class PrepareSpellsEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        return [PrepareSpellbookStep()]


class SpellAccessEffect(CardEffect):
    """Shared dispatcher for every spell-school access card."""

    access_map: ClassVar[dict[str, tuple[str, ...]]] = SPELL_ACCESS_MAP

    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        return [
            CastSpellStep(
                allowed_spell_ids=list(self.access_map.get(card.effect_id, ())),
                caster_id=str(hero.id),
            )
        ]


# The access behavior is identical; the card's effect ID selects its printed
# spell list from SPELL_ACCESS_MAP. Registering the shared class keeps future
# schools data-only instead of adding near-identical subclasses.
for _effect_id in SPELL_ACCESS_MAP:
    CardEffectRegistry.register(_effect_id, SpellAccessEffect())
