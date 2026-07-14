"""Gydion card and spell effects."""

from __future__ import annotations

from typing import ClassVar

from goa2.domain.models import (
    Card,
    CardContainerType,
    CardState,
    Hero,
    MinionType,
    TargetType,
    TokenType,
)
from goa2.domain.models.effect import DurationType, EffectScope, EffectType, Shape
from goa2.domain.state import GameState
from goa2.engine.effects import (
    CardEffect,
    CardEffectRegistry,
    register_effect,
    register_spell_effect,
)
from goa2.engine.filters_composite import AndFilter, CountMatchFilter, OrFilter
from goa2.engine.filters_geometry import InStraightLineFilter, StraightLinePathFilter
from goa2.engine.filters_hex import (
    BattleZoneFilter,
    MovementPathFilter,
    ObstacleFilter,
    RangeFilter,
    SpawnPointTeamFilter,
)
from goa2.engine.filters_units import (
    AdjacencyToContextFilter,
    CanBePlacedByActorFilter,
    MinionTypesFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.engine.stats import CardStats
from goa2.engine.steps import (
    AttackSequenceStep,
    CastSpellStep,
    CheckUnitFiltersStep,
    CreateEffectStep,
    DefeatUnitStep,
    ForceDiscardStep,
    GainCoinsStep,
    GameStep,
    MoveSequenceStep,
    MoveUnitStep,
    PlaceTokenStep,
    PlaceUnitStep,
    PrepareSpellbookStep,
    RemovePreparedSpellsStep,
    RemoveTokenStep,
    RemoveUnitStep,
    RespawnMinionAtHexStep,
    RetrieveCardStep,
    SelectStep,
    SetContextFlagStep,
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


def _outside_spell_count(state: GameState, resolving_card: Card) -> int:
    """Count this Gydion's other spells that are outside the spellbook."""
    owner = state.get_spellbook_owner()
    if owner is None:
        return 0
    return sum(
        spell.state == CardState.OUTSIDE_SPELLBOOK and spell.id != resolving_card.id
        for spell in owner.spells
    )


@register_spell_effect("vampiric_touch")
class VampiricTouchEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        retrieval_key = "vampiric_touch_retrieval"
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            SelectStep(
                target_type=TargetType.CARD,
                prompt="After the attack: You may retrieve a card",
                output_key=retrieval_key,
                card_container=CardContainerType.DISCARD,
                is_mandatory=False,
            ),
            RetrieveCardStep(card_key=retrieval_key, active_if_key=retrieval_key),
        ]


@register_spell_effect("fireball")
class FireballEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        isolated_from_friendlies = CountMatchFilter(
            min_count=0,
            max_count=0,
            sub_filters=[
                TeamFilter(relation="FRIENDLY"),
                RangeFilter(
                    min_range=1,
                    max_range=1,
                    origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY,
                ),
            ],
        )
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                target_filters=[
                    RangeFilter(min_range=2, max_range=stats.range),
                    isolated_from_friendlies,
                ],
            )
        ]


@register_spell_effect("create_undead")
class CreateUndeadEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        if hero.team is None:
            return []
        return [
            RespawnMinionAtHexStep(
                team=hero.team,
                lane_bound=True,
                hex_filters=[
                    SpawnPointTeamFilter(relation="FRIENDLY"),
                    BattleZoneFilter(),
                    ObstacleFilter(is_obstacle=False),
                    RangeFilter(max_range=stats.range),
                ],
            )
        ]


@register_spell_effect("midas_touch")
class MidasTouchEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        coins = _outside_spell_count(state, card) // 2
        if coins == 0:
            return []
        caster_key = "midas_touch_caster"
        return [
            SetContextFlagStep(key=caster_key, value=str(hero.id)),
            GainCoinsStep(hero_key=caster_key, amount=coins),
        ]


@register_spell_effect("disintegrate")
class DisintegrateEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        target_key = "disintegrate_target"
        token_key = "disintegrate_is_token"
        return [
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Remove an adjacent token or enemy melee/ranged minion",
                output_key=target_key,
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),
                    OrFilter(
                        filters=[
                            UnitTypeFilter(unit_type="TOKEN"),
                            AndFilter(
                                filters=[
                                    UnitTypeFilter(unit_type="MINION"),
                                    TeamFilter(relation="ENEMY"),
                                    MinionTypesFilter(
                                        minion_types=[MinionType.MELEE, MinionType.RANGED]
                                    ),
                                ]
                            ),
                        ]
                    ),
                ],
            ),
            CheckUnitFiltersStep(
                unit_key=target_key,
                filters=[UnitTypeFilter(unit_type="TOKEN")],
                output_key=token_key,
            ),
            RemoveTokenStep(token_key=target_key, active_if_key=token_key),
            RemoveUnitStep(unit_key=target_key, skip_if_key=token_key),
        ]


@register_spell_effect("dominate_person")
class DominatePersonEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        hero_key = "dominate_person_hero"
        victim_key = "dominate_person_minion"
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Choose an enemy hero in radius",
                output_key=hero_key,
                is_mandatory=True,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                    RangeFilter(max_range=stats.radius),
                ],
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Defeat an enemy minion adjacent to that hero",
                output_key=victim_key,
                is_mandatory=True,
                active_if_key=hero_key,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="MINION"),
                    RangeFilter(max_range=stats.radius),
                    AdjacencyToContextFilter(target_key=hero_key),
                ],
            ),
            DefeatUnitStep(victim_key=victim_key, killer_id=str(hero.id)),
        ]


@register_spell_effect("find_familiar")
class FindFamiliarEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        destination_key = "find_familiar_destination"
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Place your Familiar in radius",
                output_key=destination_key,
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.radius),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceTokenStep(token_type=TokenType.FAMILIAR, hex_key=destination_key),
            RemovePreparedSpellsStep(caster_id=str(hero.id), max_removals=3),
        ]


@register_spell_effect("dimension_door")
class DimensionDoorEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        destination_key = "dimension_door_destination"
        radius = (stats.radius or 0) + _outside_spell_count(state, card)
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"Place yourself exactly {radius} spaces away",
                output_key=destination_key,
                is_mandatory=True,
                filters=[
                    RangeFilter(min_range=radius, max_range=radius),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceUnitStep(
                unit_id=str(hero.id),
                destination_key=destination_key,
                is_mandatory=True,
            ),
        ]


@register_spell_effect("banishment")
class BanishmentEffect(CardEffect):
    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        target_key = "banishment_target"
        destination_key = "banishment_destination"
        return [
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Choose an adjacent unit or token",
                output_key=target_key,
                is_mandatory=True,
                filters=[RangeFilter(max_range=1), CanBePlacedByActorFilter()],
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Place it in an empty space in radius",
                output_key=destination_key,
                is_mandatory=True,
                active_if_key=target_key,
                filters=[
                    RangeFilter(max_range=stats.radius),
                    ObstacleFilter(is_obstacle=False, exclude_id_key=target_key),
                ],
            ),
            PlaceUnitStep(
                unit_key=target_key,
                destination_key=destination_key,
                is_mandatory=True,
            ),
        ]


# The access behavior is identical; the card's effect ID selects its printed
# spell list from SPELL_ACCESS_MAP. Registering the shared class keeps future
# schools data-only instead of adding near-identical subclasses.
for _effect_id in SPELL_ACCESS_MAP:
    CardEffectRegistry.register(_effect_id, SpellAccessEffect())
