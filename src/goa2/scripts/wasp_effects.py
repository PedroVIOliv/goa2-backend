from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import ActionType, StatType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CreateEffectStep,
    ForceDiscardStep,
    ForceDiscardOrDefeatStep,
    GameStep,
    PlaceUnitStep,
    SelectStep,
    SetContextFlagStep,
    TargetType,
)
from goa2.engine.filters import (
    ExcludeIdentityFilter,
    NotInStraightLineFilter,
    OccupiedFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
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
                restrictions=[ActionType.MOVEMENT],
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
            ForceDiscardStep(victim_key="electrocute_victim", active_if_key="electrocute_victim"),
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
                    OccupiedFilter(is_occupied=False),
                ],
            ),
            # 3. Place unit
            PlaceUnitStep(
                unit_key="telekinesis_target",
                destination_key="telekinesis_dest",
            ),
        ]


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
