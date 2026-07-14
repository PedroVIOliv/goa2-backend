"""Gydion card and spell effects."""

from __future__ import annotations

from typing import ClassVar

from goa2.domain.models import Card, Hero, TargetType
from goa2.domain.models.effect import DurationType, EffectScope, EffectType, Shape
from goa2.domain.state import GameState
from goa2.engine.effects import (
    CardEffect,
    CardEffectRegistry,
    register_effect,
    register_spell_effect,
)
from goa2.engine.filters_geometry import InStraightLineFilter, StraightLinePathFilter
from goa2.engine.filters_hex import MovementPathFilter, ObstacleFilter, RangeFilter
from goa2.engine.filters_units import TeamFilter, UnitTypeFilter
from goa2.engine.stats import CardStats
from goa2.engine.steps import (
    AttackSequenceStep,
    CastSpellStep,
    CreateEffectStep,
    ForceDiscardStep,
    GameStep,
    MoveSequenceStep,
    MoveUnitStep,
    PrepareSpellbookStep,
    SelectStep,
)

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


@register_spell_effect("shocking_grasp")
class ShockingGraspEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        target_key = "shocking_grasp_target"
        destination_key = "shocking_grasp_destination"
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target an adjacent enemy unit",
                output_key=target_key,
                is_mandatory=True,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                ],
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                target_id_key=target_key,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="After the attack: You may move the target up to 1 space",
                output_key=destination_key,
                is_mandatory=False,
                active_if_key=target_key,
                filters=[
                    RangeFilter(max_range=1, origin_key=target_key),
                    ObstacleFilter(is_obstacle=False, exclude_id_key=target_key),
                    MovementPathFilter(range_val=1, unit_key=target_key),
                ],
            ),
            MoveUnitStep(
                unit_key=target_key,
                destination_key=destination_key,
                range_val=1,
                is_mandatory=False,
                is_movement_action=False,
                active_if_key=destination_key,
            ),
        ]


@register_spell_effect("magic_missile")
class MagicMissileEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                target_filters=[RangeFilter(min_range=2, max_range=stats.range)],
            )
        ]


@register_spell_effect("expeditious_retreat")
class ExpeditiousRetreatEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        return [
            MoveSequenceStep(
                unit_id=str(hero.id),
                range_val=stats.primary_value,
                force_straight_line=True,
            )
        ]


@register_spell_effect("burning_hands")
class BurningHandsEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        target_key = "burning_hands_target"
        victim_key = "burning_hands_discard_victim"
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target an adjacent enemy unit",
                output_key=target_key,
                is_mandatory=True,
                filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=1)],
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Choose an enemy hero adjacent to the target to discard",
                output_key=victim_key,
                is_mandatory=False,
                active_if_key=target_key,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                    RangeFilter(
                        min_range=1,
                        max_range=1,
                        origin_key=target_key,
                    ),
                ],
            ),
            ForceDiscardStep(victim_key=victim_key, active_if_key=victim_key),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                target_id_key=target_key,
            ),
        ]


@register_spell_effect("suggestion")
class SuggestionEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        target_key = "suggestion_target"
        destination_key = "suggestion_destination"
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Choose an enemy hero in radius",
                output_key=target_key,
                is_mandatory=True,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                    RangeFilter(max_range=stats.radius),
                ],
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Move that hero exactly 3 spaces in a straight line",
                output_key=destination_key,
                is_mandatory=True,
                active_if_key=target_key,
                filters=[
                    RangeFilter(min_range=3, max_range=3, origin_key=target_key),
                    InStraightLineFilter(origin_key=target_key),
                    StraightLinePathFilter(origin_key=target_key),
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=3, unit_key=target_key),
                ],
            ),
            MoveUnitStep(
                unit_key=target_key,
                destination_key=destination_key,
                range_val=3,
                is_movement_action=False,
            ),
        ]


@register_spell_effect("shield")
class ShieldEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        already_exists = any(
            effect.effect_type == EffectType.ATTACK_IMMUNITY
            and effect.source_id == str(hero.id)
            and effect.source_card_id == card.id
            for effect in state.active_effects
        )
        if already_exists:
            return []
        return [
            CreateEffectStep(
                effect_type=EffectType.ATTACK_IMMUNITY,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                basic_attacks_only=True,
                is_active=True,
                source_card_id=card.id,
                use_context_card=False,
            )
        ]


# The access behavior is identical; the card's effect ID selects its printed
# spell list from SPELL_ACCESS_MAP. Registering the shared class keeps future
# schools data-only instead of adding near-identical subclasses.
for _effect_id in SPELL_ACCESS_MAP:
    CardEffectRegistry.register(_effect_id, SpellAccessEffect())
