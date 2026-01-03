from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    GameStep, StepResult, SelectStep, SwapUnitsStep, PlaceUnitStep, 
    AttackSequenceStep
)
from goa2.engine.filters import (
    UnitTypeFilter, TeamFilter, RangeFilter, OccupiedFilter, 
    SpawnPointFilter, AdjacentSpawnPointFilter,
    AdjacencyToContextFilter, ExcludeIdentityFilter, HasEmptyNeighborFilter,
    ForcedMovementByEnemyFilter, ImmunityFilter
)

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
        damage = card.primary_action_value or 0
        
        return [
            # 1. Select Attack Target (Mandatory)
            SelectStep(
                target_type="UNIT",
                prompt="Select target for Noble Blade attack",
                output_key="victim_id",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                    ImmunityFilter() # Standard attack immunity check
                ],
                is_mandatory=True
            ),
            
            # 2. Select Unit to Nudge (Optional)
            SelectStep(
                target_type="UNIT",
                prompt="Select adjacent unit to move 1 space (Optional)",
                output_key="nudge_unit_id",
                is_mandatory=False,
                filters=[
                    AdjacencyToContextFilter(target_key="victim_id"),
                    ExcludeIdentityFilter(exclude_self=True, exclude_keys=["victim_id"]),
                    ImmunityFilter(), # Cannot move immune units
                    HasEmptyNeighborFilter(), # Must have somewhere to go
                    ForcedMovementByEnemyFilter() # Cannot move if protected
                ]
            ),
            
            # 3. Select Destination (Active If Nudge Selected)
            SelectStep(
                target_type="HEX",
                prompt="Select destination for move",
                output_key="nudge_dest",
                active_if_key="nudge_unit_id",
                filters=[
                    RangeFilter(max_range=1, origin_key="nudge_unit_id"),
                    OccupiedFilter(is_occupied=False)
                ],
                is_mandatory=True 
            ),
            
            # 4. Execute Move (Active If Nudge Selected)
            PlaceUnitStep(
                unit_key="nudge_unit_id",
                destination_key="nudge_dest",
                active_if_key="nudge_unit_id"
            ),
            
            # 5. Resolve Attack Sequence (Using pre-selected target)
            AttackSequenceStep(
                damage=damage, 
                target_id_key="victim_id",
                range_val=1
            )
        ]

@register_effect("arcane_whirlpool")
class SwapEnemyMinionEffect(CardEffect):
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        return [
            SelectStep(
                target_type="UNIT",
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=card.range_value)
                ],
                prompt="Select an enemy minion to swap with.",
                output_key="swap_target_id"
            ),
            SwapWithSelectedStep(hero_id=hero.id)
        ]

class SwapWithSelectedStep(GameStep):
    type: str = "swap_with_selected"
    hero_id: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        target_id = context.get("swap_target_id")
        if target_id:
             # SwapUnitsStep swaps unit_a and unit_b positions
             return StepResult(is_finished=True, new_steps=[
                 SwapUnitsStep(unit_a_id=self.hero_id, unit_b_id=target_id)
             ])
        return StepResult(is_finished=True)

@register_effect("liquid_leap")
@register_effect("magical_current")
class TeleportStrictEffect(CardEffect):
    """
    Card text: "Place yourself into a space in range without a spawn point 
    and not adjacent to an empty spawn point."
    Used by: Liquid Leap, Magical Current
    """
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        range_val = card.range_value if card.range_value is not None else 0
        
        return [
            SelectStep(
                target_type="HEX",
                prompt="Select destination for Teleport",
                output_key="target_hex",
                filters=[
                    RangeFilter(max_range=range_val),
                    OccupiedFilter(is_occupied=False),
                    SpawnPointFilter(has_spawn_point=False),
                    AdjacentSpawnPointFilter(is_empty=True, must_not_have=True)
                ],
                is_mandatory=True
            ),
            PlaceUnitStep(unit_id=hero.id, destination_key="target_hex")
        ]

@register_effect("stranger_tide")
class TeleportNoSpawnEffect(CardEffect):
    """
    Card text: "Place yourself into a space in range without a spawn point."
    Used by: Stranger Tide
    """
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        range_val = card.range_value if card.range_value is not None else 0
        
        return [
            SelectStep(
                target_type="HEX",
                prompt="Select destination for Teleport",
                output_key="target_hex",
                filters=[
                    RangeFilter(max_range=range_val),
                    OccupiedFilter(is_occupied=False),
                    SpawnPointFilter(has_spawn_point=False)
                ],
                is_mandatory=True
            ),
            PlaceUnitStep(unit_id=hero.id, destination_key="target_hex")
        ]
