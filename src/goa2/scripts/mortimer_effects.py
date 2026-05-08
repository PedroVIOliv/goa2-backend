from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models.enums import TargetType, TokenType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.filters_composite import AndFilter, OrFilter
from goa2.engine.filters_hex import ObstacleFilter, RangeFilter, SpawnPointFilter
from goa2.engine.filters_units import ExcludeIdentityFilter
from goa2.engine.steps import GameStep, PlaceTokenStep, SelectStep

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


def _awaken_placement_steps(radius: int) -> list[GameStep]:
    steps: list[GameStep] = []
    prior_keys: list[str] = []

    for i in range(4):
        key = f"zombie_hex_{i}"
        filters = [
            ObstacleFilter(is_obstacle=False),
            OrFilter(
                filters=[
                    RangeFilter(min_range=1, max_range=1),
                    AndFilter(
                        filters=[
                            RangeFilter(max_range=radius),
                            SpawnPointFilter(has_spawn_point=True),
                        ]
                    ),
                ]
            ),
        ]
        if prior_keys:
            filters.append(ExcludeIdentityFilter(exclude_self=False, exclude_keys=list(prior_keys)))

        steps.append(
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"Select hex for Zombie token {i + 1}/4 (optional)",
                output_key=key,
                is_mandatory=False,
                filters=filters,
            )
        )
        prior_keys.append(key)

    for i in range(4):
        steps.append(PlaceTokenStep(token_type=TokenType.ZOMBIE, hex_key=f"zombie_hex_{i}"))

    return steps


@register_effect("awaken")
class AwakenEffect(CardEffect):
    """Place up to 4 Zombie tokens adjacent to you or into spawn points in radius."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _awaken_placement_steps(stats.radius)
