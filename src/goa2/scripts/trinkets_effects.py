"""Trinkets card effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models.enums import CardContainerType, TargetType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.filters_hex import ObstacleFilter, RangeFilter
from goa2.engine.steps import (
    CheckContextConditionStep,
    GameStep,
    MoveUnitStep,
    PlaceTurretStep,
    RemoveTurretStep,
    RetrieveCardStep,
    SelectStep,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


@register_effect("salvage_parts")
class SalvagePartsEffect(CardEffect):
    """
    Choose one:
    - Place the Turret into a space adjacent to you; it counts as an obstacle.
    - Remove the Turret; move up to 3 spaces.
    - Remove the Turret; you may retrieve a discarded card.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="salvage_choice",
                number_options=[1, 2, 3],
                number_labels={
                    1: "Place the Turret adjacent to you",
                    2: "Remove the Turret and move up to 3 spaces",
                    3: "Remove the Turret and retrieve a discarded card",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="salvage_choice",
                operator="==",
                threshold=1,
                output_key="salvage_place_turret",
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select an adjacent space for the Turret",
                output_key="salvage_turret_hex",
                active_if_key="salvage_place_turret",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceTurretStep(
                hex_key="salvage_turret_hex",
                owner_id=str(hero.id),
                active_if_key="salvage_turret_hex",
                output_key="salvage_turret_id",
            ),
            CheckContextConditionStep(
                input_key="salvage_choice",
                operator="==",
                threshold=2,
                output_key="salvage_remove_move",
            ),
            RemoveTurretStep(active_if_key="salvage_remove_move"),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select destination (up to 3 spaces)",
                output_key="salvage_move_hex",
                active_if_key="salvage_remove_move",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=3),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            MoveUnitStep(
                unit_id=str(hero.id),
                destination_key="salvage_move_hex",
                range_val=3,
                active_if_key="salvage_move_hex",
            ),
            CheckContextConditionStep(
                input_key="salvage_choice",
                operator="==",
                threshold=3,
                output_key="salvage_remove_retrieve",
            ),
            RemoveTurretStep(active_if_key="salvage_remove_retrieve"),
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="Select a discarded card to retrieve",
                output_key="salvage_retrieved_card",
                active_if_key="salvage_remove_retrieve",
                is_mandatory=False,
            ),
            RetrieveCardStep(
                card_key="salvage_retrieved_card",
                active_if_key="salvage_retrieved_card",
            ),
        ]
