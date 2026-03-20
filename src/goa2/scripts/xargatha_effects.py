from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING
from goa2.engine.effects import CardEffect, MovementAura, StatAura, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CountAdjacentEnemiesStep,
    CountStep,
    CreateEffectStep,
    DefeatUnitStep,
    GameStep,
    MayRepeatOnceStep,
    MoveSequenceStep,
    MoveUnitStep,
    RetrieveCardStep,
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
    MinionTypesFilter,
)
from goa2.domain.models.enums import (
    CardContainerType,
    StatType,
    TargetType,
    MinionType,
    ActionType,
)
from goa2.domain.models.effect import (
    DurationType,
    EffectScope,
    EffectType,
    Shape,
    AffectsFilter,
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
                        target_filters=[
                            UnitTypeFilter(unit_type="HERO"),
                            ExcludeIdentityFilter(exclude_keys=["victim_id"]),
                        ],
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
                range_val=stats.range or 0,
                is_ranged=True,
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
        base_range = stats.range or 0
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
                is_ranged=True,
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
                        is_ranged=True,
                        range_bonus_key="adj_rng_bonus",
                        target_filters=[
                            UnitTypeFilter(unit_type="HERO"),
                            ExcludeIdentityFilter(exclude_keys=["victim_id"]),
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


@register_effect("charm")
class CharmEffect(CardEffect):
    """
    Card Text: "Before or after movement, you may move an enemy ranged minion in radius up to 2 spaces."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy ranged minion in radius (or skip to select after movement instead)",
                output_key="charmed_minion",
                filters=[
                    RangeFilter(max_range=stats.radius or 0),
                    TeamFilter(relation="ENEMY"),
                    MinionTypesFilter(minion_types=[MinionType.RANGED]),
                ],
                is_mandatory=False,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space up to 2 spaces away to move the minion to.",
                output_key="charm_dest",
                filters=[
                    RangeFilter(max_range=2, origin_key="charmed_minion"),
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=2, unit_key="charmed_minion"),
                ],
                is_mandatory=False,  # "you may"
                active_if_key="charmed_minion",
            ),
            MoveUnitStep(
                unit_key="charmed_minion",
                destination_key="charm_dest",
                range_val=2,
                is_movement_action=False,
                active_if_key="charm_dest",
            ),
            MoveSequenceStep(
                range_val=stats.primary_value,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy ranged minion in radius",
                output_key="charmed_minion_after",
                filters=[
                    RangeFilter(max_range=stats.radius or 0),
                    TeamFilter(relation="ENEMY"),
                    MinionTypesFilter(minion_types=[MinionType.RANGED]),
                ],
                is_mandatory=False,
                skip_if_key="charmed_minion",  # Skip if already used before movement
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space up to 2 spaces away to move the minion to.",
                output_key="charm_dest_after",
                filters=[
                    RangeFilter(max_range=2, origin_key="charmed_minion_after"),
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=2, unit_key="charmed_minion"),
                ],
                is_mandatory=False,  # "you may"
                active_if_key="charmed_minion_after",
            ),
            MoveUnitStep(
                unit_key="charmed_minion_after",
                destination_key="charm_dest_after",
                range_val=2,
                is_movement_action=False,
                active_if_key="charm_dest_after",
            ),
        ]


@register_effect("control")
class ControlEffect(CardEffect):
    """
    Card Text: "Before or after movement, you may move an enemy ranged or melee minion in radius up to 2 spaces."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy ranged or melee minion in radius (or skip to select after movement instead)",
                output_key="charmed_minion",
                filters=[
                    RangeFilter(max_range=stats.radius or 0),
                    TeamFilter(relation="ENEMY"),
                    MinionTypesFilter(
                        minion_types=[MinionType.RANGED, MinionType.MELEE]
                    ),
                ],
                is_mandatory=False,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space up to 2 spaces away to move the minion to.",
                output_key="charm_dest",
                filters=[
                    RangeFilter(max_range=2, origin_key="charmed_minion"),
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=2, unit_key="charmed_minion"),
                ],
                is_mandatory=False,  # "you may"
                active_if_key="charmed_minion",
            ),
            MoveUnitStep(
                unit_key="charmed_minion",
                destination_key="charm_dest",
                range_val=2,
                is_movement_action=False,
                active_if_key="charm_dest",
            ),
            MoveSequenceStep(
                range_val=stats.primary_value,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy ranged or melee minion in radius",
                output_key="charmed_minion_after",
                filters=[
                    RangeFilter(max_range=stats.radius or 0),
                    TeamFilter(relation="ENEMY"),
                    MinionTypesFilter(
                        minion_types=[MinionType.RANGED, MinionType.MELEE]
                    ),
                ],
                is_mandatory=False,
                skip_if_key="charmed_minion",  # Skip if already used before movement
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space up to 2 spaces away to move the minion to.",
                output_key="charm_dest_after",
                filters=[
                    RangeFilter(max_range=2, origin_key="charmed_minion_after"),
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=2, unit_key="charmed_minion"),
                ],
                is_mandatory=False,  # "you may"
                active_if_key="charmed_minion_after",
            ),
            MoveUnitStep(
                unit_key="charmed_minion_after",
                destination_key="charm_dest_after",
                range_val=2,
                is_movement_action=False,
                active_if_key="charm_dest_after",
            ),
        ]


@register_effect("dominate")
class DominateEffect(CardEffect):
    """
    Card Text: "Before or after movement, you may move an enemy minion in radius up to 2 spaces; ignore heavy minion immunity."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy minion in radius (or skip to select after movement instead)",
                output_key="charmed_minion",
                filters=[
                    RangeFilter(max_range=stats.radius or 0),
                    TeamFilter(relation="ENEMY"),
                    MinionTypesFilter(
                        minion_types=[
                            MinionType.RANGED,
                            MinionType.MELEE,
                            MinionType.HEAVY,
                        ]
                    ),
                ],
                is_mandatory=False,
                skip_immunity_filter=True,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space up to 2 spaces away to move the minion to.",
                output_key="charm_dest",
                filters=[
                    RangeFilter(max_range=2, origin_key="charmed_minion"),
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=2, unit_key="charmed_minion"),
                ],
                is_mandatory=False,  # "you may"
                active_if_key="charmed_minion",
            ),
            MoveUnitStep(
                unit_key="charmed_minion",
                destination_key="charm_dest",
                range_val=2,
                is_movement_action=False,
                active_if_key="charm_dest",
            ),
            MoveSequenceStep(
                range_val=stats.primary_value,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy minion in radius",
                output_key="charmed_minion_after",
                filters=[
                    RangeFilter(max_range=stats.radius or 0),
                    TeamFilter(relation="ENEMY"),
                    MinionTypesFilter(
                        minion_types=[
                            MinionType.RANGED,
                            MinionType.MELEE,
                            MinionType.HEAVY,
                        ]
                    ),
                ],
                is_mandatory=False,
                skip_if_key="charmed_minion",  # Skip if already used before movement
                skip_immunity_filter=True,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space up to 2 spaces away to move the minion to.",
                output_key="charm_dest_after",
                filters=[
                    RangeFilter(max_range=2, origin_key="charmed_minion_after"),
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=2, unit_key="charmed_minion"),
                ],
                is_mandatory=False,  # "you may"
                active_if_key="charmed_minion_after",
            ),
            MoveUnitStep(
                unit_key="charmed_minion_after",
                destination_key="charm_dest_after",
                range_val=2,
                is_movement_action=False,
                active_if_key="charm_dest_after",
            ),
        ]


@register_effect("final_embrace")
class FinalEmbraceEffect(CardEffect):
    """
    Card Text: "End of round: Defeat an enemy melee or ranged minion adjacent to you."

    Creates a DELAYED_TRIGGER effect with finishing steps that execute when the
    effect expires at end of round. The finishing steps select and defeat an
    adjacent enemy melee or ranged minion.
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            CreateEffectStep(
                effect_type=EffectType.DELAYED_TRIGGER,
                duration=DurationType.THIS_ROUND,
                scope=EffectScope(shape=Shape.POINT),
                is_active=True,
                finishing_steps=[
                    SelectStep(
                        target_type=TargetType.UNIT,
                        filters=[
                            TeamFilter(relation="ENEMY"),
                            MinionTypesFilter(
                                minion_types=[MinionType.MELEE, MinionType.RANGED]
                            ),
                            RangeFilter(max_range=1),
                        ],
                        output_key="final_embrace_victim",
                        is_mandatory=True,
                        prompt="Select enemy melee or ranged minion to defeat (Final Embrace)",
                    ),
                    DefeatUnitStep(
                        victim_key="final_embrace_victim",
                        active_if_key="final_embrace_victim",
                    ),
                ],
            ),
        ]


@register_effect("constrict")
class ConstrictEffect(CardEffect):
    """
    Card Text: "End of round: Defeat an enemy melee minion adjacent to you. (Before the end of round minion battle.)"

    Creates a DELAYED_TRIGGER effect with finishing steps that execute when the
    effect expires at end of round. The finishing steps select and defeat an
    adjacent enemy melee or ranged minion.
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            CreateEffectStep(
                effect_type=EffectType.DELAYED_TRIGGER,
                duration=DurationType.THIS_ROUND,
                scope=EffectScope(shape=Shape.POINT),
                is_active=True,
                finishing_steps=[
                    SelectStep(
                        target_type=TargetType.UNIT,
                        filters=[
                            TeamFilter(relation="ENEMY"),
                            MinionTypesFilter(minion_types=[MinionType.MELEE]),
                            RangeFilter(max_range=1),
                        ],
                        output_key="constrict_victim",
                        is_mandatory=True,
                        prompt="Select enemy melee minion to defeat (Constrict)",
                    ),
                    DefeatUnitStep(
                        victim_key="constrict_victim",
                        active_if_key="constrict_victim",
                    ),
                ],
            ),
        ]


@register_effect("devoted_followers")
class DevotedFollowersEffect(CardEffect):
    """
    Card Text: "If you are adjacent to an enemy unit, you may retrieve a discarded card."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            CountStep(
                target_type=TargetType.UNIT,
                filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
                output_key="adjacent_enemy_count",
            ),
            CheckContextConditionStep(
                input_key="adjacent_enemy_count",
                operator=">=",
                threshold=1,
                output_key="has_adjacent_enemy",
            ),
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="Select a discarded card to retrieve",
                output_key="retrieved_card",
                is_mandatory=False,
                active_if_key="has_adjacent_enemy",
            ),
            RetrieveCardStep(
                card_key="retrieved_card",
                active_if_key="retrieved_card",
            ),
        ]


@register_effect("fresh_converts")
class FreshConvertsEffect(CardEffect):
    """
    Card Text: "If you are adjacent to an enemy minion, you may retrieve a discarded card."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            CountStep(
                target_type=TargetType.UNIT,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="MINION"),
                ],
                output_key="adjacent_minion_count",
            ),
            CheckContextConditionStep(
                input_key="adjacent_minion_count",
                operator=">=",
                threshold=1,
                output_key="has_adjacent_minion",
            ),
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="Select a discarded card to retrieve",
                output_key="retrieved_card",
                is_mandatory=False,
                active_if_key="has_adjacent_minion",
            ),
            RetrieveCardStep(
                card_key="retrieved_card",
                active_if_key="retrieved_card",
            ),
        ]


@register_effect("turn_into_statues")
class TurnIntoStatuesEffect(CardEffect):
    """Next turn: Enemy heroes in radius count as terrain and cannot move."""

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            CreateEffectStep(
                effect_type=EffectType.PETRIFY,
                duration=DurationType.NEXT_TURN,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
                is_active=True,
            ),
        ]


@register_effect("petrifying_stare")
class PetrifyingStareEffect(TurnIntoStatuesEffect):
    pass


@register_effect("stone_gaze")
class StoneGazeEffect(TurnIntoStatuesEffect):
    pass


@register_effect("metamorphosis")
class MetamorphosisEffect(CardEffect):
    """
    Ultimate: "Gain +1 Movement and +1 Initiative for each enemy unit
    adjacent to you. You may move through obstacles."
    """

    def get_stat_auras(self) -> List[StatAura]:
        return [
            StatAura(
                stat_type=StatType.MOVEMENT,
                count_filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=1)],
                multiplier=1,
            ),
            StatAura(
                stat_type=StatType.INITIATIVE,
                count_filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=1)],
                multiplier=1,
            ),
        ]

    def get_movement_aura(self) -> Optional[MovementAura]:
        return MovementAura(pass_through_obstacles=True)

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return []
