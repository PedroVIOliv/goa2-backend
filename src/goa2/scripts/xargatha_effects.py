from __future__ import annotations
from typing import List, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CountAdjacentEnemiesStep,
    GameStep,
    MayRepeatOnceStep,
    MoveUnitStep,
    SelectStep,
)
from goa2.engine.filters import (
    ExcludeIdentityFilter,
    ForcedMovementByEnemyFilter,
    MovementPathFilter,
    ObstacleFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models.enums import TargetType

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


@register_effect("cleave")
class CleaveEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you. After the attack: May repeat
    once on a different enemy hero. (You may repeat even if the original
    target was a minion.)"

    Steps:
    1. Attack adjacent target
    2. May repeat once on a different enemy hero
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Attack adjacent target
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # 2. May repeat on a different enemy hero
            MayRepeatOnceStep(
                steps_template=[
                    AttackSequenceStep(
                        damage=stats.primary_value,
                        range_val=1,
                        target_filters=[UnitTypeFilter(unit_type="HERO")],
                    ),
                ],
            ),
        ]


@register_effect("threatening_slash")
class ThreateningSlashEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you. +1 Attack for each other
    enemy unit adjacent to you. (Do not count the target when calculating
    the attack bonus.)"

    Uses CountAdjacentEnemiesStep to compute bonus at resolve time,
    then AttackSequenceStep reads the bonus from context.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CountAdjacentEnemiesStep(
                output_key="adj_atk_bonus", multiplier=1, subtract=1
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                damage_bonus_key="adj_atk_bonus",
            ),
        ]


@register_effect("deadly_swipe")
class DeadlySwipeEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you. +2 Attack for each other
    enemy unit adjacent to you."

    Same as Threatening Slash but +2 per adjacent enemy.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CountAdjacentEnemiesStep(
                output_key="adj_atk_bonus", multiplier=2, subtract=1
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                damage_bonus_key="adj_atk_bonus",
            ),
        ]


@register_effect("lethal_spin")
class LethalSpinEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you. +3 Attack for each other
    enemy unit adjacent to you."

    Same as Threatening Slash but +3 per adjacent enemy.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CountAdjacentEnemiesStep(
                output_key="adj_atk_bonus", multiplier=3, subtract=1
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                damage_bonus_key="adj_atk_bonus",
            ),
        ]


@register_effect("long_thrust")
class LongThrustEffect(CardEffect):
    """
    Card Text: "Target a unit in range. +1 Range for each enemy unit
    adjacent to you."

    Ranged attack where range increases by 1 per adjacent enemy.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CountAdjacentEnemiesStep(
                output_key="adj_rng_bonus", multiplier=1, subtract=0
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range or 1,
                range_bonus_key="adj_rng_bonus",
            ),
        ]


@register_effect("rapid_thrusts")
class RapidThrustsEffect(CardEffect):
    """
    Card Text: "Target a unit in range. +1 Range for each enemy unit
    adjacent to you. May repeat once on a different enemy hero."

    Uses CountAdjacentEnemiesStep before EACH attack so the range bonus
    is recalculated (adjacent count may change after first attack).
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        base_range = stats.range or 1
        return [
            # 1. Count adjacent enemies for range bonus
            CountAdjacentEnemiesStep(
                output_key="adj_rng_bonus", multiplier=1, subtract=0
            ),
            # 2. Attack with dynamic range (AttackSequenceStep handles selection
            #    with the correct effective range from range_bonus_key)
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=base_range,
                range_bonus_key="adj_rng_bonus",
            ),
            # 3. Recount + repeat on different enemy hero
            MayRepeatOnceStep(
                steps_template=[
                    CountAdjacentEnemiesStep(
                        output_key="adj_rng_bonus", multiplier=1, subtract=0
                    ),
                    AttackSequenceStep(
                        damage=stats.primary_value,
                        range_val=base_range,
                        range_bonus_key="adj_rng_bonus",
                        target_filters=[
                            UnitTypeFilter(unit_type="HERO"),
                            ExcludeIdentityFilter(
                                exclude_keys=["victim_id"]
                            ),
                        ],
                    ),
                ],
            ),
        ]


@register_effect("sirens_call")
class SirensCallEffect(CardEffect):
    """
    Card Text: "Target an enemy unit not adjacent to you and in range;
    if able, move the target up to 3 spaces to a space adjacent to you."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Select enemy unit: not adjacent (min_range=2), in range
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy unit not adjacent to you and in range.",
                output_key="sirens_call_target",
                filters=[
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range, min_range=2),
                    ForcedMovementByEnemyFilter(),
                ],
                is_mandatory=True,
            ),
            # 2. Select destination: adjacent to Xargatha, reachable by target
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space adjacent to you to move the target to.",
                output_key="sirens_call_dest",
                filters=[
                    RangeFilter(max_range=1),
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=3, unit_key="sirens_call_target"),
                ],
                is_mandatory=False,  # "if able"
            ),
            # 3. Move target to destination (forced movement, not a movement action)
            MoveUnitStep(
                unit_key="sirens_call_target",
                destination_key="sirens_call_dest",
                range_val=3,
                is_movement_action=False,
                active_if_key="sirens_call_dest",
            ),
        ]
