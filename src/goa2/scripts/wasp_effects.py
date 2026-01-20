from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import ActionType, DisplacementType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckUnitTypeStep,
    CombineBooleanContextStep,
    CreateEffectStep,
    ForceDiscardStep,
    ForceDiscardOrDefeatStep,
    ForEachStep,
    GameStep,
    MayRepeatOnceStep,
    MayRepeatNTimesStep,
    MultiSelectStep,
    PlaceUnitStep,
    PushUnitStep,
    SelectStep,
    SetContextFlagStep,
    TargetType,
)
from goa2.engine.filters import (
    ExcludeIdentityFilter,
    NotInStraightLineFilter,
    ObstacleFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
    AdjacencyToContextFilter,
    PreserveDistanceFilter,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


@register_effect("stop_projectiles")
class StopProjectilesEffect(CardEffect):
    """
    Card text: "Block a ranged attack."

    This is a primary DEFENSE card. The effect triggers when used to defend.
    - If attack is ranged: auto_block = True (block succeeds regardless of values)
    - If attack is melee: defense_invalid = True (defense fails entirely)
    """

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        if context.get("attack_is_ranged"):
            return [SetContextFlagStep(key="auto_block", value=True)]
        else:
            return [SetContextFlagStep(key="defense_invalid", value=True)]


@register_effect("magnetic_dagger")
class MagneticDaggerEffect(CardEffect):
    """
    Card Text: "Attack. This Turn: Enemy heroes in Radius 3 cannot be
    placed or swapped by enemy actions."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Standard attack
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # 2. Create placement prevention effect
            CreateEffectStep(
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                displacement_blocks=[DisplacementType.PLACE, DisplacementType.SWAP],
                blocks_enemy_actors=True,
                blocks_friendly_actors=False,
                blocks_self=False,
            ),
        ]


@register_effect("charged_boomerang")
class ChargedBoomerangEffect(CardEffect):
    """
    Card Text: "Target a unit in range and not in a straight line.
    (Units adjacent to you are in a straight line from you.)"

    This is a ranged attack with a targeting restriction:
    - Cannot target units in a straight line from Wasp
    - Adjacent units are implicitly in a straight line
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                target_filters=[NotInStraightLineFilter()],
            ),
        ]


@register_effect("shock")
class ShockEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you. After the attack:
    An enemy hero in radius and not adjacent to you discards a card, if able."

    Steps:
    1. Attack adjacent target (range=1)
    2. Select enemy hero in radius but not adjacent (optional)
    3. Force that hero to discard a card
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Attack adjacent target
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # 2. Select enemy hero in radius but not adjacent (min_range=2)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero in radius to discard (optional)",
                output_key="shock_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius or 2, min_range=2),
                ],
            ),
            # 3. Force discard
            ForceDiscardStep(victim_key="shock_victim", active_if_key="shock_victim"),
        ]


@register_effect("electrocute")
class ElectrocuteEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you. After the attack:
    An enemy hero in radius and not adjacent to you discards a card, if able."

    Same as Shock - the difference is in the card's radius stat.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Attack adjacent target
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # 2. Select enemy hero in radius but not adjacent (min_range=2)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero in radius to discard (optional)",
                output_key="electrocute_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius or 3, min_range=2),
                ],
            ),
            # 3. Force discard
            ForceDiscardStep(
                victim_key="electrocute_victim", active_if_key="electrocute_victim"
            ),
        ]


@register_effect("telekinesis")
class TelekinesisEffect(CardEffect):
    """
    Card Text: "Place a unit or a token in range, which is not in a straight line,
    into a space adjacent to you."

    Steps:
    1. Select unit in range, not in straight line
    2. Select destination adjacent to Wasp
    3. Place unit at destination
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Select unit or token in range, not in straight line
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select unit to teleport",
                output_key="telekinesis_target",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.range or 3),
                    NotInStraightLineFilter(),
                ],
            ),
            # 2. Select destination adjacent to Wasp
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select destination adjacent to you",
                output_key="telekinesis_dest",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            # 3. Place unit
            PlaceUnitStep(
                unit_key="telekinesis_target",
                destination_key="telekinesis_dest",
            ),
        ]


@register_effect("mass_telekinesis")
class MassTelekinesisEffect(CardEffect):
    """
    Card Text: "Place a unit or a token in range, which is not in a straight line,
    into a space adjacent to you. May repeat once."

    Steps:
    1. Select unit in range, not in straight line
    2. Select destination adjacent to Wasp
    3. Place unit at destination
    4. Repeat once
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        effect_steps = [
            # 1. Select unit or token in range, not in straight line
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select unit to teleport",
                output_key="telekinesis_target",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.range or 3),
                    NotInStraightLineFilter(),
                ],
            ),
            # 2. Select destination adjacent to Wasp
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select destination adjacent to you",
                output_key="telekinesis_dest",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            # 3. Place unit
            PlaceUnitStep(
                unit_key="telekinesis_target",
                destination_key="telekinesis_dest",
            ),
        ]
        repeat = MayRepeatOnceStep(steps_template=effect_steps)
        return effect_steps + [repeat]


@register_effect("electroblast")
class ElectroblastEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you. After the attack:
    An enemy hero in radius and not adjacent to you discards a card, or is defeated."

    Similar to Shock but uses ForceDiscardOrDefeatStep instead.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Attack adjacent target
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # 2. Select enemy hero in radius but not adjacent
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero in radius to discard/defeat (optional)",
                output_key="electroblast_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius or 3, min_range=2),
                ],
            ),
            # 3. Force discard or defeat
            ForceDiscardOrDefeatStep(victim_key="electroblast_victim"),
        ]


@register_effect("thunder_boomerang")
class ThunderBoomerangEffect(CardEffect):
    """
    Card Text: "Target a unit in range and not in a straight line.
    After the attack: If you targeted a hero, may repeat once on a different target."

    Steps:
    1. Select target (not in straight line)
    2. Attack using pre-selected target
    3. Check if target was a hero
    4. If hero: may repeat once on different target
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Select target with NotInStraightLineFilter FIRST
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select attack target (not in straight line)",
                output_key="thunder_target_1",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.range or 3),
                    TeamFilter(relation="ENEMY"),
                    NotInStraightLineFilter(),
                ],
            ),
            # 2. Attack using pre-selected target
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range or 3,
                target_id_key="thunder_target_1",
            ),
            # 3. Check if target was a hero
            CheckUnitTypeStep(
                unit_key="thunder_target_1",
                expected_type="HERO",
                output_key="can_repeat_thunder",
            ),
            # 4. Conditional repeat on different target
            MayRepeatOnceStep(
                active_if_key="can_repeat_thunder",
                steps_template=[
                    SelectStep(
                        target_type=TargetType.UNIT,
                        prompt="Select second target (not in straight line)",
                        output_key="thunder_target_2",
                        is_mandatory=False,
                        filters=[
                            RangeFilter(max_range=stats.range or 3),
                            TeamFilter(relation="ENEMY"),
                            NotInStraightLineFilter(),
                            ExcludeIdentityFilter(exclude_keys=["thunder_target_1"]),
                        ],
                    ),
                    AttackSequenceStep(
                        damage=stats.primary_value,
                        range_val=stats.range or 3,
                        target_id_key="thunder_target_2",
                    ),
                ],
            ),
        ]


@register_effect("reflect_projectiles")
class ReflectProjectilesEffect(CardEffect):
    """
    Card Text: "Block a ranged attack; if you do, an enemy hero in range
    discards a card, if able."

    Defense card that:
    - Only works against ranged attacks
    - On successful block, triggers discard effect
    """

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        if context.get("attack_is_ranged"):
            return [SetContextFlagStep(key="auto_block", value=True)]
        else:
            return [SetContextFlagStep(key="defense_invalid", value=True)]

    def build_on_block_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: Dict[str, Any],
    ) -> List[GameStep]:
        """Triggered only if block succeeded."""
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero in range to discard",
                output_key="reflect_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range or 3),
                ],
            ),
            ForceDiscardStep(victim_key="reflect_victim"),
        ]


@register_effect("deflect_projectiles")
class DeflectProjectilesEffect(CardEffect):
    """
    Card Text: "Block a ranged attack; if you do, an enemy hero in range,
    other than the attacker, discards a card, if able."

    Same as Reflect Projectiles but excludes the attacker from discard targeting.
    """

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        if context.get("attack_is_ranged"):
            return [SetContextFlagStep(key="auto_block", value=True)]
        else:
            return [SetContextFlagStep(key="defense_invalid", value=True)]

    def build_on_block_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: Dict[str, Any],
    ) -> List[GameStep]:
        """Triggered only if block succeeded. Excludes the attacker."""
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero in range to discard (not attacker)",
                output_key="deflect_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range or 3),
                    ExcludeIdentityFilter(exclude_keys=["attacker_id"]),
                ],
            ),
            ForceDiscardStep(victim_key="deflect_victim"),
        ]


@register_effect("lift_up")
class LiftUpEffect(CardEffect):
    """
    Card Text: "Move a unit, or a token, in radius 1 space, without moving it
    away from you or closer to you. May repeat once on the same target."

    Orbit mechanic: Distance from origin must be preserved.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        orbit_steps = [
            # 2. Select destination adjacent to target + preserving distance
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select orbit destination (distance preserved)",
                output_key="lift_dest",
                is_mandatory=True,
                filters=[
                    AdjacencyToContextFilter(target_key="lift_target"),
                    PreserveDistanceFilter(target_key="lift_target"),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            # 3. Place unit at destination
            PlaceUnitStep(
                unit_key="lift_target",
                destination_key="lift_dest",
            ),
        ]

        steps: List[GameStep] = [
            # 1. Select unit or token in radius
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select unit to lift",
                output_key="lift_target",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.radius or 2),
                ],
            ),
        ]
        return steps + orbit_steps + [MayRepeatOnceStep(steps_template=orbit_steps)]


@register_effect("control_gravity")
class ControlGravityEffect(LiftUpEffect):
    """
    Card Text: "Move a unit, or a token, in radius 1 space, without moving it
    away from you or closer to you. May repeat once on the same target."

    Inherits logic from Lift Up but uses card stats (Radius 3).
    """

    pass


@register_effect("center_of_mass")
class CenterOfMassEffect(LiftUpEffect):
    """
    Card Text: "Move a unit, or a token, in radius 1 space, without moving it
    away from you or closer to you. May repeat up to two times on the same target."

    Inherits logic from Lift Up/Control Gravity but repeats TWICE.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        orbit_steps = [
            # 2. Select destination adjacent to target + preserving distance
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select orbit destination (distance preserved)",
                output_key="lift_dest",
                is_mandatory=True,
                filters=[
                    AdjacencyToContextFilter(target_key="lift_target"),
                    PreserveDistanceFilter(target_key="lift_target"),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            # 3. Place unit at destination
            PlaceUnitStep(
                unit_key="lift_target",
                destination_key="lift_dest",
            ),
        ]

        steps: List[GameStep] = [
            # 1. Select unit or token in radius
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select unit to lift",
                output_key="lift_target",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.radius or 3),
                ],
            ),
        ]
        # Repeat up to 2 times
        return (
            steps
            + orbit_steps
            + [
                MayRepeatNTimesStep(
                    steps_template=orbit_steps, max_repeats=2, prompt="Repeat orbit?"
                )
            ]
        )


@register_effect("kinetic_repulse")
class KineticRepulseEffect(CardEffect):
    """
    Card Text: "Push up to 2 enemy units adjacent to you 3 spaces;
    if a pushed hero is stopped by an obstacle, that hero discards a card, if able."

    Steps:
    1. Select up to 2 adjacent enemies (MultiSelectStep)
    2. For each selected unit:
       a. Push 3 spaces with collision detection
       b. Check if unit is hero
       c. Combine: collision AND is_hero
       d. If both true, force discard
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Select up to 2 adjacent enemies
            MultiSelectStep(
                target_type=TargetType.UNIT,
                prompt="Select up to 2 adjacent enemies to push",
                output_key="push_targets",
                max_selections=2,
                min_selections=0,  # Optional - can push 0, 1, or 2
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            # 2. Process each push
            ForEachStep(
                list_key="push_targets",
                item_key="current_push_target",
                steps_template=[
                    # Push with collision detection
                    PushUnitStep(
                        target_key="current_push_target",
                        distance=3,
                        collision_output_key="push_collision",
                    ),
                    # Check if pushed unit is a hero
                    CheckUnitTypeStep(
                        unit_key="current_push_target",
                        expected_type="HERO",
                        output_key="is_hero",
                    ),
                    # Combine checks: collision AND hero
                    CombineBooleanContextStep(
                        key_a="push_collision",
                        key_b="is_hero",
                        output_key="should_discard",
                        operation="AND",
                    ),
                    # Force discard only if both conditions are true
                    ForceDiscardStep(
                        victim_key="current_push_target",
                        active_if_key="should_discard",
                    ),
                ],
            ),
        ]


@register_effect("kinetic_blast")
class KineticBlastEffect(CardEffect):
    """
    Card Text: "Push up to 2 enemy units adjacent to you 3 or 4 spaces;
    if a pushed hero is stopped by an obstacle, that hero discards a card, if able."

    Same as Kinetic Repulse but with choice of push distance (3 or 4).
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Choose push distance (3 or 4)
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance",
                output_key="push_distance",
                number_options=[3, 4],
                is_mandatory=True,
            ),
            # 2. Select up to 2 adjacent enemies
            MultiSelectStep(
                target_type=TargetType.UNIT,
                prompt="Select up to 2 adjacent enemies to push",
                output_key="push_targets",
                max_selections=2,
                min_selections=0,
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            # 3. Process each push
            ForEachStep(
                list_key="push_targets",
                item_key="current_push_target",
                steps_template=[
                    # Push with collision detection (distance from context)
                    PushUnitStep(
                        target_key="current_push_target",
                        distance_key="push_distance",
                        collision_output_key="push_collision",
                    ),
                    # Check if pushed unit is a hero
                    CheckUnitTypeStep(
                        unit_key="current_push_target",
                        expected_type="HERO",
                        output_key="is_hero",
                    ),
                    # Combine checks: collision AND hero
                    CombineBooleanContextStep(
                        key_a="push_collision",
                        key_b="is_hero",
                        output_key="should_discard",
                        operation="AND",
                    ),
                    # Force discard only if both conditions are true
                    ForceDiscardStep(
                        victim_key="current_push_target",
                        active_if_key="should_discard",
                    ),
                ],
            ),
        ]
