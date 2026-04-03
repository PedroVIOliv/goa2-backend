from __future__ import annotations
from typing import List, TYPE_CHECKING
from goa2.domain.models.effect import (
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import TokenType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    CreateEffectStep,
    GameStep,
    PlaceTokenStep,
    SelectStep,
    TargetType,
)
from goa2.engine.filters import (
    ObstacleFilter,
    RangeFilter,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


@register_effect("smoke_bomb")
class SmokeBombEffect(CardEffect):
    """
    Place the Smoke bomb token in radius; enemy heroes cannot target you or
    another unit if the Smoke bomb token is on a straight line between that
    enemy hero and their target.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Place Smoke Bomb token",
                output_key="smoke_bomb_hex",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.radius),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceTokenStep(
                token_type=TokenType.SMOKE_BOMB,
                hex_key="smoke_bomb_hex",
                output_key="smoke_bomb_token_id",
            ),
            CreateEffectStep(
                effect_type=EffectType.LOS_BLOCKER,
                scope=EffectScope(shape=Shape.POINT),
                origin_id_key="smoke_bomb_token_id",
                is_token_effect=True,
                duration=DurationType.PASSIVE,
            ),
        ]
