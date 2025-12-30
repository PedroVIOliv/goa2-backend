from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import GameStep, StepResult, SelectStep, SwapUnitsStep
from goa2.engine.filters import UnitTypeFilter, TeamFilter, RangeFilter

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card

@register_effect("effect_swap_enemy_minion")
class SwapEnemyMinionEffect(CardEffect):
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        return [
            SelectStep(
                player_id=hero.id,
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
