from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import GameStep, StepResult, SelectStep, SwapUnitsStep, PlaceUnitStep
from goa2.engine.filters import (
    UnitTypeFilter, TeamFilter, RangeFilter, OccupiedFilter, 
    SpawnPointFilter, AdjacentSpawnPointFilter
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card

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
