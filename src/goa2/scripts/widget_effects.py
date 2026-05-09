"""Widget card effects.

Remaining useful precedents:
- Min smoke-bomb effects: single-token placement, selection, and swaps.
- Mortimer zombie effects: optional token movement and repeated choice gates.
- Bain/Brogan/Arien effects: straight-line targeting and discard-or-defeat flows.
- Ursafar effects: selecting a card and using PerformPrimaryActionStep.
- Misa/Silverarrow/Tigerclaw effects: computed or related follow-up movement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models.enums import TargetType, TokenType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.filters_composite import OrFilter
from goa2.engine.filters_hex import MovementPathFilter, ObstacleFilter, RangeFilter
from goa2.engine.filters_units import TeamFilter, TokenTypeFilter, UnitTypeFilter
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    GameStep,
    MoveTokenStep,
    MoveUnitStep,
    PlaceTokenStep,
    SelectStep,
    SetContextFlagStep,
    SwapUnitsStep,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


def _pyro_selection_step(output_key: str, range_val: int, *, is_mandatory: bool) -> SelectStep:
    return SelectStep(
        target_type=TargetType.UNIT_OR_TOKEN,
        prompt="Select Pyro",
        output_key=output_key,
        is_mandatory=is_mandatory,
        auto_select_if_one=True,
        filters=[
            UnitTypeFilter(unit_type="TOKEN"),
            TokenTypeFilter(token_type=TokenType.PYRO),
            RangeFilter(max_range=range_val),
        ],
    )


def _move_pyro_steps(
    *,
    range_val: int,
    move_distance: int,
    pyro_key: str = "pyro_id",
    destination_key: str = "pyro_dest",
    is_mandatory: bool = False,
    active_if_key: str | None = None,
) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Select Pyro to move",
            output_key=pyro_key,
            is_mandatory=is_mandatory,
            active_if_key=active_if_key,
            auto_select_if_one=True,
            filters=[
                UnitTypeFilter(unit_type="TOKEN"),
                TokenTypeFilter(token_type=TokenType.PYRO),
                RangeFilter(max_range=range_val),
            ],
        ),
        SelectStep(
            target_type=TargetType.HEX,
            prompt=f"Select Pyro destination (up to {move_distance})",
            output_key=destination_key,
            is_mandatory=False,
            active_if_key=pyro_key,
            filters=[
                ObstacleFilter(is_obstacle=False),
                MovementPathFilter(range_val=move_distance, unit_key=pyro_key),
            ],
        ),
        MoveTokenStep(
            token_key=pyro_key,
            destination_key=destination_key,
            range_val=move_distance,
            active_if_key=destination_key,
        ),
    ]


def _move_selected_pyro_steps(
    *,
    pyro_key: str,
    destination_key: str,
    move_distance: int,
    active_if_key: str | None,
) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.HEX,
            prompt=f"Select Pyro destination (up to {move_distance})",
            output_key=destination_key,
            is_mandatory=False,
            active_if_key=active_if_key,
            filters=[
                ObstacleFilter(is_obstacle=False),
                MovementPathFilter(range_val=move_distance, unit_key=pyro_key),
            ],
        ),
        MoveTokenStep(
            token_key=pyro_key,
            destination_key=destination_key,
            range_val=move_distance,
            active_if_key=destination_key,
        ),
    ]


def _move_widget_steps(
    *,
    hero_id: str,
    destination_key: str,
    active_if_key: str | None,
) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Select Widget destination (up to 2)",
            output_key=destination_key,
            active_if_key=active_if_key,
            is_mandatory=False,
            filters=[
                ObstacleFilter(is_obstacle=False),
                MovementPathFilter(range_val=2, unit_id=hero_id),
            ],
        ),
        MoveUnitStep(
            unit_id=hero_id,
            destination_key=destination_key,
            range_val=2,
            active_if_key=destination_key,
        ),
    ]


def _swap_with_pyro_steps(range_val: int, *, is_mandatory: bool = True) -> list[GameStep]:
    return [
        _pyro_selection_step("pyro_swap_id", range_val, is_mandatory=is_mandatory),
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select yourself or a friendly hero to swap with Pyro",
            output_key="pyro_swap_target",
            is_mandatory=is_mandatory,
            active_if_key="pyro_swap_id",
            skip_self_filter=True,
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                OrFilter(
                    filters=[
                        TeamFilter(relation="SELF"),
                        TeamFilter(relation="FRIENDLY"),
                    ]
                ),
                RangeFilter(max_range=range_val),
            ],
        ),
        SwapUnitsStep(
            unit_a_key="pyro_swap_id",
            unit_b_key="pyro_swap_target",
            active_if_key="pyro_swap_target",
            is_mandatory=is_mandatory,
        ),
    ]


def _diversionary_steps(damage: int, pyro_move: int) -> list[GameStep]:
    return [
        AttackSequenceStep(damage=damage, range_val=1),
        *_move_pyro_steps(range_val=99, move_distance=pyro_move, is_mandatory=False),
    ]


@register_effect("dragon_bond")
class DragonBondEffect(CardEffect):
    """Choose to place Pyro, or move Widget and Pyro if Pyro is already in play."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SetContextFlagStep(key="widget_id", value=str(hero.id)),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="dragon_bond_choice",
                number_options=[1, 2],
                number_labels={
                    1: "Place Pyro into a space in radius",
                    2: "Move yourself and Pyro up to 2 spaces",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="dragon_bond_choice",
                operator="==",
                threshold=1,
                output_key="dragon_bond_place",
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space in radius for Pyro",
                output_key="pyro_place_hex",
                active_if_key="dragon_bond_place",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.radius),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceTokenStep(
                token_type=TokenType.PYRO,
                hex_key="pyro_place_hex",
                active_if_key="pyro_place_hex",
            ),
            CheckContextConditionStep(
                input_key="dragon_bond_choice",
                operator="==",
                threshold=2,
                output_key="dragon_bond_move",
            ),
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select Pyro in play",
                output_key="dragon_bond_pyro",
                active_if_key="dragon_bond_move",
                is_mandatory=True,
                auto_select_if_one=True,
                filters=[
                    UnitTypeFilter(unit_type="TOKEN"),
                    TokenTypeFilter(token_type=TokenType.PYRO),
                    RangeFilter(max_range=99),
                ],
            ),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose who moves first",
                output_key="dragon_bond_order",
                active_if_key="dragon_bond_pyro",
                number_options=[1, 2],
                number_labels={
                    1: "Move Widget first",
                    2: "Move Pyro first",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="dragon_bond_order",
                operator="==",
                threshold=1,
                output_key="dragon_bond_widget_first",
            ),
            *_move_widget_steps(
                hero_id=str(hero.id),
                destination_key="dragon_bond_widget_dest_first",
                active_if_key="dragon_bond_widget_first",
            ),
            *_move_selected_pyro_steps(
                pyro_key="dragon_bond_pyro",
                destination_key="dragon_bond_pyro_dest_second",
                move_distance=2,
                active_if_key="dragon_bond_widget_first",
            ),
            CheckContextConditionStep(
                input_key="dragon_bond_order",
                operator="==",
                threshold=2,
                output_key="dragon_bond_pyro_first",
            ),
            *_move_selected_pyro_steps(
                pyro_key="dragon_bond_pyro",
                destination_key="dragon_bond_pyro_dest_first",
                move_distance=2,
                active_if_key="dragon_bond_pyro_first",
            ),
            *_move_widget_steps(
                hero_id=str(hero.id),
                destination_key="dragon_bond_widget_dest_second",
                active_if_key="dragon_bond_pyro_first",
            ),
        ]


@register_effect("take_off")
class TakeOffEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _swap_with_pyro_steps(stats.range)


@register_effect("all_aboard")
class AllAboardEffect(TakeOffEffect):
    pass


@register_effect("diversionary_strike")
class DiversionaryStrikeEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _diversionary_steps(stats.primary_value, 2)


@register_effect("diversionary_attack")
class DiversionaryAttackEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _diversionary_steps(stats.primary_value, 3)


@register_effect("diversionary_assault")
class DiversionaryAssaultEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _diversionary_steps(stats.primary_value, 4)
