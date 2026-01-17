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
from goa2.engine.stats import compute_card_stats
from goa2.engine.steps import (
    AttackSequenceStep,
    CreateEffectStep,
    GameStep,
    SetContextFlagStep,
)
from goa2.engine.filters import NotInStraightLineFilter

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


@register_effect("magnetic_dagger")
class MagneticDaggerEffect(CardEffect):
    """
    Card Text: "Attack. This Turn: Enemy heroes in Radius 3 cannot be
    placed or swapped by enemy actions."
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        stats = compute_card_stats(state, hero.id, card)

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

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        stats = compute_card_stats(state, hero.id, card)

        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                target_filters=[NotInStraightLineFilter()],
            ),
        ]
