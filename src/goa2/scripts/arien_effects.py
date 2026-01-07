from __future__ import annotations
from typing import List, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    GameStep,
    SelectStep,
    SwapUnitsStep,
    PlaceUnitStep,
    AttackSequenceStep,
    PushUnitStep,
)
from goa2.engine.filters import (
    UnitTypeFilter,
    TeamFilter,
    RangeFilter,
    OccupiedFilter,
    SpawnPointFilter,
    AdjacentSpawnPointFilter,
    AdjacencyToContextFilter,
    ExcludeIdentityFilter,
    HasEmptyNeighborFilter,
    ForcedMovementByEnemyFilter,
    ImmunityFilter,
)
from goa2.engine.stats import compute_card_stats

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card


@register_effect("noble_blade")
class NobleBladeEffect(CardEffect):
    """
    Card text: "Target a unit adjacent to you. Before the attack: You may move another unit
    that is adjacent to the target 1 space."
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        stats = compute_card_stats(state, hero.id, card)

        return [
            # 1. Select Attack Target (Mandatory)
            SelectStep(
                target_type="UNIT",
                prompt="Select target for Noble Blade attack",
                output_key="victim_id",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                    ImmunityFilter(),  # Standard attack immunity check
                ],
                is_mandatory=True,
            ),
            # 2. Select Unit to Nudge (Optional)
            SelectStep(
                target_type="UNIT",
                prompt="Select adjacent unit to move 1 space (Optional)",
                output_key="nudge_unit_id",
                is_mandatory=False,
                filters=[
                    AdjacencyToContextFilter(target_key="victim_id"),
                    ExcludeIdentityFilter(
                        exclude_self=True, exclude_keys=["victim_id"]
                    ),
                    ImmunityFilter(),  # Cannot move immune units
                    HasEmptyNeighborFilter(),  # Must have somewhere to go
                    ForcedMovementByEnemyFilter(),  # Cannot move if protected
                ],
            ),
            # 3. Select Destination (Active If Nudge Selected)
            SelectStep(
                target_type="HEX",
                prompt="Select destination for move",
                output_key="nudge_dest",
                active_if_key="nudge_unit_id",
                filters=[
                    RangeFilter(max_range=1, origin_key="nudge_unit_id"),
                    OccupiedFilter(is_occupied=False),
                ],
                is_mandatory=True,
            ),
            # 4. Execute Move (Active If Nudge Selected)
            PlaceUnitStep(
                unit_key="nudge_unit_id",
                destination_key="nudge_dest",
                active_if_key="nudge_unit_id",
            ),
            # 5. Resolve Attack Sequence (Using pre-selected target)
            # Note: range_val=1 is hardcoded as Noble Blade is adjacent-only (not buffable)
            AttackSequenceStep(
                damage=stats.primary_value, target_id_key="victim_id", range_val=1
            ),
        ]


@register_effect("arcane_whirlpool")
class SwapEnemyMinionEffect(CardEffect):
    """
    Card text: "Swap with an enemy minion in range."
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        stats = compute_card_stats(state, hero.id, card)

        return [
            SelectStep(
                target_type="UNIT",
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                    ImmunityFilter(),
                ],
                prompt="Select an enemy minion to swap with.",
                output_key="swap_target_id",
            ),
            SwapUnitsStep(unit_a_id=hero.id, unit_b_key="swap_target_id"),
        ]


@register_effect("liquid_leap")
@register_effect("magical_current")
class TeleportStrictEffect(CardEffect):
    """
    Card text: "Place yourself into a space in range without a spawn point
    and not adjacent to an empty spawn point."
    Used by: Liquid Leap, Magical Current
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        stats = compute_card_stats(state, hero.id, card)

        return [
            SelectStep(
                target_type="HEX",
                prompt="Select destination for Teleport",
                output_key="target_hex",
                filters=[
                    RangeFilter(max_range=stats.range),
                    OccupiedFilter(is_occupied=False),
                    SpawnPointFilter(has_spawn_point=False),
                    AdjacentSpawnPointFilter(is_empty=True, must_not_have=True),
                ],
                is_mandatory=True,
            ),
            PlaceUnitStep(unit_id=hero.id, destination_key="target_hex"),
        ]


@register_effect("stranger_tide")
class TeleportNoSpawnEffect(CardEffect):
    """
    Card text: "Place yourself into a space in range without a spawn point."
    Used by: Stranger Tide
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        stats = compute_card_stats(state, hero.id, card)

        return [
            SelectStep(
                target_type="HEX",
                prompt="Select destination for Teleport",
                output_key="target_hex",
                filters=[
                    RangeFilter(max_range=stats.range),
                    OccupiedFilter(is_occupied=False),
                    SpawnPointFilter(has_spawn_point=False),
                ],
                is_mandatory=True,
            ),
            PlaceUnitStep(unit_id=hero.id, destination_key="target_hex"),
        ]


@register_effect("rogue_wave")
class RogueWaveEffect(CardEffect):
    """
    Card text: "Target a unit in range. After the attack: You may push an enemy unit
    adjacent to you up to 2 spaces."
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        stats = compute_card_stats(state, hero.id, card)

        return [
            # 1. Attack Sequence (selects target, reaction, damage)
            AttackSequenceStep(damage=stats.primary_value, range_val=stats.range),
            # 2. Optional: Select enemy adjacent to push
            SelectStep(
                target_type="UNIT",
                prompt="Select an adjacent enemy to push (optional)",
                output_key="push_target_id",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),  # Adjacent to Arien
                    TeamFilter(relation="ENEMY"),
                    ImmunityFilter(),  # Cannot push immune units
                ],
            ),
            # 3. Choose push distance (0, 1, or 2) - only if target selected
            SelectStep(
                target_type="NUMBER",
                prompt="Choose push distance (0-2)",
                output_key="push_distance",
                number_options=[0, 1, 2],
                active_if_key="push_target_id",
            ),
            # 4. Execute push - reads target and distance from context
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
                is_mandatory=False,
            ),
        ]
