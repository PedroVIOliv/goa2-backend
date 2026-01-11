from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    GameStep,
    SetContextFlagStep,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card


@register_effect("stop_projectiles")
class StopProjectilesEffect(CardEffect):
    """
    Card text: "Block a ranged attack."

    This is a primary DEFENSE card. The effect triggers when used to defend.
    - If attack is ranged: auto_block = True (block succeeds regardless of values)
    - If attack is melee: defense_invalid = True (defense fails entirely)
    """

    def get_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        if context.get("attack_is_ranged"):
            return [SetContextFlagStep(key="auto_block", value=True)]
        else:
            return [SetContextFlagStep(key="defense_invalid", value=True)]
