from __future__ import annotations
from typing import List, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CountAdjacentEnemiesStep,
    GameStep,
    MayRepeatOnceStep,
)
from goa2.engine.filters import (
    ExcludeIdentityFilter,
    UnitTypeFilter,
)

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
