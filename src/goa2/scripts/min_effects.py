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
    ExcludeIdentityFilter,
    ObstacleFilter,
    RangeFilter,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


def _mine_placement_steps(
    stats: "CardStats", blast_count: int, dud_count: int
) -> List["GameStep"]:
    """Build steps to select all mine hexes first, then place them all."""
    steps: List["GameStep"] = []
    hex_keys: List[tuple[str, TokenType]] = []
    prior_keys: List[str] = []

    # Select blast hexes
    for i in range(blast_count):
        key = f"blast_hex_{i}"
        label = f"blast mine {i + 1}/{blast_count}" if blast_count > 1 else "blast mine"
        filters = [
            RangeFilter(max_range=stats.radius),
            ObstacleFilter(is_obstacle=False),
        ]
        if prior_keys:
            filters.append(
                ExcludeIdentityFilter(exclude_self=False, exclude_keys=list(prior_keys))
            )
        steps.append(
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"Select hex for {label}",
                output_key=key,
                is_mandatory=True,
                filters=filters,
            ),
        )
        hex_keys.append((key, TokenType.MINE_BLAST))
        prior_keys.append(key)

    # Select dud hexes
    for i in range(dud_count):
        key = f"dud_hex_{i}"
        label = f"dud mine {i + 1}/{dud_count}" if dud_count > 1 else "dud mine"
        filters = [
            RangeFilter(max_range=stats.radius),
            ObstacleFilter(is_obstacle=False),
        ]
        if prior_keys:
            filters.append(
                ExcludeIdentityFilter(exclude_self=False, exclude_keys=list(prior_keys))
            )
        steps.append(
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"Select hex for {label}",
                output_key=key,
                is_mandatory=True,
                filters=filters,
            ),
        )
        hex_keys.append((key, TokenType.MINE_DUD))
        prior_keys.append(key)

    # Place all tokens after all selections
    for key, token_type in hex_keys:
        steps.append(
            PlaceTokenStep(
                token_type=token_type,
                hex_key=key,
            ),
        )

    return steps


@register_effect("trip_mine")
class TripMineEffect(CardEffect):
    """Place 2 Mine tokens, 1 blast and 1 dud, facedown in radius."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return _mine_placement_steps(stats, blast_count=1, dud_count=1)


@register_effect("cluster_mine")
class ClusterMineEffect(CardEffect):
    """Place 3 Mine tokens, 1 blast and 2 duds, facedown in radius."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return _mine_placement_steps(stats, blast_count=1, dud_count=2)


@register_effect("minefield")
class MinefieldEffect(CardEffect):
    """Place 3 Mine tokens, 2 blasts and 1 dud, facedown in radius."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return _mine_placement_steps(stats, blast_count=2, dud_count=1)


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
