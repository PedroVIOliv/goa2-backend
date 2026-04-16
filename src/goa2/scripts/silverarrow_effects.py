from __future__ import annotations
from typing import List, TYPE_CHECKING

from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CheckUnitTypeStep,
    CreateEffectStep,
    FastTravelSequenceStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    GameStep,
    SelectStep,
)
from goa2.engine.filters import (
    ExcludeIdentityFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models import (
    ActionType,
    DurationType,
    EffectType,
    TargetType,
)
from goa2.domain.models.effect import AffectsFilter, EffectScope, Shape

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


# =============================================================================
# FAMILY 2 — RED: Maximum-Range Snipe (Long Shot, Rain of Arrows)
# =============================================================================


@register_effect("long_shot")
class LongShotEffect(CardEffect):
    """Card text: Target a unit at maximum range."""

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List[GameStep]:
        r = stats.range or 0
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=r,
                is_ranged=True,
                target_filters=[RangeFilter(min_range=r, max_range=r)],
            ),
        ]


@register_effect("rain_of_arrows")
class RainOfArrowsEffect(CardEffect):
    """
    Card text:
    "Target a unit at maximum range.
    If you target a hero, repeat once on a different hero;
    if you do, may repeat once on a minion."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List[GameStep]:
        r = stats.range or 0
        dmg = stats.primary_value
        return [
            # 1. First attack — any unit at max range.
            AttackSequenceStep(
                damage=dmg,
                range_val=r,
                is_ranged=True,
                target_id_key="rain_victim_1",
                target_filters=[RangeFilter(min_range=r, max_range=r)],
            ),
            # 2. Was the first target a hero? Convert bool -> True/None gate.
            CheckUnitTypeStep(
                unit_key="rain_victim_1",
                expected_type="HERO",
                output_key="_rain_first_is_hero",
            ),
            CheckContextConditionStep(
                input_key="_rain_first_is_hero",
                operator="==",
                threshold=1,
                output_key="rain_first_was_hero",
            ),
            # 3. Mandatory second hero shot (different hero, max range).
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select a different enemy hero at maximum range",
                output_key="rain_victim_2",
                is_mandatory=True,
                active_if_key="rain_first_was_hero",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(min_range=r, max_range=r),
                    ExcludeIdentityFilter(exclude_keys=["rain_victim_1"]),
                ],
            ),
            AttackSequenceStep(
                damage=dmg,
                range_val=r,
                is_ranged=True,
                target_id_key="rain_victim_2",
                active_if_key="rain_victim_2",
            ),
            # 4. Optional third minion shot (only if second shot resolved).
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="You may target a different enemy minion at maximum range",
                output_key="rain_victim_3",
                is_mandatory=False,
                active_if_key="rain_victim_2",
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(min_range=r, max_range=r),
                    ExcludeIdentityFilter(
                        exclude_keys=["rain_victim_1", "rain_victim_2"]
                    ),
                ],
            ),
            AttackSequenceStep(
                damage=dmg,
                range_val=r,
                is_ranged=True,
                target_id_key="rain_victim_3",
                active_if_key="rain_victim_3",
            ),
        ]


# =============================================================================
# FAMILY 3 — BLUE: Root Zones (Grappling Branches / Entangling Vines / Grasping Roots)
# =============================================================================


class _RootZoneEffect(CardEffect):
    """
    "This turn: Enemy heroes in radius cannot fast travel,
    or move more than 1 space with a movement action."

    Identical to Arien's Deluge (minus the trailing MoveSequenceStep).
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                max_value=1,
                limit_actions_only=True,
                restrictions=[ActionType.FAST_TRAVEL],
            ),
        ]


@register_effect("grappling_branches")
class GrapplingBranchesEffect(_RootZoneEffect):
    pass


@register_effect("entangling_vines")
class EntanglingVinesEffect(_RootZoneEffect):
    pass


@register_effect("grasping_roots")
class GraspingRootsEffect(_RootZoneEffect):
    pass


# =============================================================================
# FAMILY 4 — BLUE: End-of-Turn Sentinel (Treetop Sentinel / Warning Shot)
# =============================================================================


def _sentinel_finishing_steps(
    hero_id: str, radius: int, defeat_on_fail: bool
) -> List[GameStep]:
    discard_step: GameStep = (
        ForceDiscardOrDefeatStep(victim_key="sentinel_victim")
        if defeat_on_fail
        else ForceDiscardStep(victim_key="sentinel_victim")
    )
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="End of turn — select an enemy hero in radius",
            output_key="sentinel_victim",
            is_mandatory=True,
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=radius, origin_id=hero_id),
            ],
        ),
        discard_step,
    ]


@register_effect("treetop_sentinel")
class TreetopSentinelEffect(CardEffect):
    """
    "End of turn: An enemy hero in radius discards a card, or is defeated."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List[GameStep]:
        radius = stats.radius or 0
        return [
            CreateEffectStep(
                effect_type=EffectType.DELAYED_TRIGGER,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                is_active=True,
                finishing_steps=_sentinel_finishing_steps(
                    str(hero.id), radius, defeat_on_fail=True
                ),
            ),
        ]


@register_effect("warning_shot")
class WarningShotEffect(CardEffect):
    """
    "End of turn: An enemy hero in radius discards a card, if able."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List[GameStep]:
        radius = stats.radius or 0
        return [
            CreateEffectStep(
                effect_type=EffectType.DELAYED_TRIGGER,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                is_active=True,
                finishing_steps=_sentinel_finishing_steps(
                    str(hero.id), radius, defeat_on_fail=False
                ),
            ),
        ]


# =============================================================================
# FAMILY 7 — GOLD: Shoot and Scoot (untiered)
# =============================================================================


@register_effect("shoot_and_scoot")
class ShootAndScootEffect(CardEffect):
    """
    "Target a unit at maximum range.
    After the attack: If able, you may fast travel to an adjacent zone."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List[GameStep]:
        r = stats.range or 0
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=r,
                is_ranged=True,
                target_filters=[RangeFilter(min_range=r, max_range=r)],
            ),
            FastTravelSequenceStep(unit_id=str(hero.id)),
        ]
