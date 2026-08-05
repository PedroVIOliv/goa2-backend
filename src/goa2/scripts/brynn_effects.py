"""Brynn card effects.

Brynn is an obstacle-synergy ranger: nearly every card gains a bonus or
unlocks a clause when an enemy hero is "adjacent to 3 or more obstacles".
That positional check is implemented by AdjacentToObstaclesFilter, which also
honours her ultimate ("Over the Top": all enemy heroes count as adjacent to
3+ obstacles while she performs actions).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models.enums import ActionType, CardContainerType, TargetType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.filters import (
    AdjacentToObstaclesFilter,
    AndFilter,
    CanBeMovedByActorFilter,
    ExcludeIdentityFilter,
    ImmunityFilter,
    MovementPathFilter,
    ObstacleFilter,
    OrFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CheckUnitFiltersStep,
    CountStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    GameStep,
    MayRepeatOnceStep,
    MoveUnitStep,
    RetrieveCardStep,
    SelectStep,
    SetContextFlagStep,
    SwapUnitsStep,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


# ---------------------------------------------------------------------------
# Blue chain — Swaps: Tread Lightly / Cover Tracks / Hide Traces
# ---------------------------------------------------------------------------


def _swap_target_filters(radius: int | None) -> list:
    """Swap target set: any adjacent unit, or an enemy hero in radius who is
    adjacent to 3+ obstacles. Immune units are never valid (immunity blocks
    swaps, even beneficial ones)."""
    return [
        OrFilter(
            filters=[
                RangeFilter(max_range=1),
                AndFilter(
                    filters=[
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="HERO"),
                        RangeFilter(max_range=radius),
                        AdjacentToObstaclesFilter(min_count=3),
                    ]
                ),
            ]
        ),
        ImmunityFilter(),
    ]


def _self_move_steps(hero_id: str, distance: int) -> list[GameStep]:
    """Optional 'move up to N spaces' for Brynn herself (effect-side movement,
    not a movement action)."""
    return [
        SelectStep(
            target_type=TargetType.HEX,
            prompt=f"You may move up to {distance} spaces",
            output_key="brynn_move_dest",
            is_mandatory=False,
            filters=[
                RangeFilter(max_range=distance),
                MovementPathFilter(range_val=distance, unit_id=hero_id),
                ObstacleFilter(is_obstacle=False),
            ],
        ),
        MoveUnitStep(
            unit_id=hero_id,
            destination_key="brynn_move_dest",
            range_val=distance,
            active_if_key="brynn_move_dest",
        ),
    ]


class _SwapEffect(CardEffect):
    """Swap with a valid target; optionally move afterwards."""

    move_distance: int = 0

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps: list[GameStep] = [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select a unit to swap with",
                output_key="swap_target",
                is_mandatory=True,
                filters=_swap_target_filters(stats.radius),
            ),
            SwapUnitsStep(unit_a_id=hero.id, unit_b_key="swap_target"),
        ]
        if self.move_distance:
            steps.extend(_self_move_steps(hero.id, self.move_distance))
        return steps


@register_effect("tread_lightly")
class TreadLightlyEffect(_SwapEffect):
    """Swap with either a unit adjacent to you, or with an enemy hero in radius
    who is adjacent to 3+ obstacles."""

    move_distance: int = 0


@register_effect("cover_tracks")
class CoverTracksEffect(_SwapEffect):
    """Tread Lightly + you may move 1 space."""

    move_distance: int = 1


@register_effect("hide_traces")
class HideTracesEffect(_SwapEffect):
    """Tread Lightly + move up to 2 spaces."""

    move_distance: int = 2


# ---------------------------------------------------------------------------
# Blue chain — Move friendly: Mountain Guide (2) / Expedition Leader (3)
# ---------------------------------------------------------------------------


class _MoveFriendlyEffect(CardEffect):
    """Move a friendly unit adjacent to you up to N spaces. If an enemy hero in
    radius is adjacent to 3+ obstacles, move a different friendly unit in radius
    up to N spaces."""

    move_distance: int = 2

    def _move_unit_block(
        self,
        *,
        unit_key: str,
        dest_key: str,
        select_filters: list,
        select_prompt: str,
        gate_key: str | None,
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt=select_prompt,
                output_key=unit_key,
                is_mandatory=False,
                filters=select_filters,
                active_if_key=gate_key,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"Move the unit up to {self.move_distance} spaces",
                output_key=dest_key,
                is_mandatory=False,
                active_if_key=unit_key,
                filters=[
                    RangeFilter(max_range=self.move_distance, origin_key=unit_key),
                    MovementPathFilter(range_val=self.move_distance, unit_key=unit_key),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            MoveUnitStep(
                unit_key=unit_key,
                destination_key=dest_key,
                range_val=self.move_distance,
                active_if_key=dest_key,
            ),
        ]

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps: list[GameStep] = self._move_unit_block(
            unit_key="mg_unit1",
            dest_key="mg_dest1",
            select_prompt="You may move a friendly unit adjacent to you",
            gate_key=None,
            select_filters=[
                TeamFilter(relation="FRIENDLY"),
                RangeFilter(max_range=1),
            ],
        )
        # Second move is gated on an enemy hero in radius adjacent to 3+ obstacles.
        steps.append(
            CountStep(
                target_type=TargetType.UNIT,
                output_key="mg_enemy_count",
                filters=[
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                    RangeFilter(max_range=stats.radius),
                    AdjacentToObstaclesFilter(min_count=3),
                ],
            )
        )
        steps.append(
            CheckContextConditionStep(
                input_key="mg_enemy_count",
                operator=">=",
                threshold=1,
                output_key="mg_has_enemy",
            )
        )
        steps.extend(
            self._move_unit_block(
                unit_key="mg_unit2",
                dest_key="mg_dest2",
                select_prompt="Move a different friendly unit in radius",
                gate_key="mg_has_enemy",
                select_filters=[
                    TeamFilter(relation="FRIENDLY"),
                    RangeFilter(max_range=stats.radius),
                    ExcludeIdentityFilter(exclude_keys=["mg_unit1"]),
                ],
            )
        )
        return steps


@register_effect("mountain_guide")
class MountainGuideEffect(_MoveFriendlyEffect):
    move_distance: int = 2


@register_effect("expedition_leader")
class ExpeditionLeaderEffect(_MoveFriendlyEffect):
    move_distance: int = 3


# ---------------------------------------------------------------------------
# Green chain — Traps: Bear Trap / Log Trap (discard) / Deadfall Trap (or defeat)
# ---------------------------------------------------------------------------


class _TrapEffect(CardEffect):
    """Target an adjacent enemy hero or one in radius adjacent to 3+ obstacles."""

    defeat_on_no_card: bool = False

    def _resolve_step(self) -> GameStep:
        if self.defeat_on_no_card:
            return ForceDiscardOrDefeatStep(victim_key="trap_victim")
        return ForceDiscardStep(victim_key="trap_victim")

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an adjacent or qualifying enemy hero in radius",
                output_key="trap_victim",
                is_mandatory=True,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                    OrFilter(
                        filters=[
                            RangeFilter(max_range=1),
                            AndFilter(
                                filters=[
                                    RangeFilter(max_range=stats.radius),
                                    AdjacentToObstaclesFilter(min_count=3),
                                ]
                            ),
                        ]
                    ),
                ],
            ),
            self._resolve_step(),
        ]


@register_effect("bear_trap")
class BearTrapEffect(_TrapEffect):
    defeat_on_no_card: bool = False


@register_effect("log_trap")
class LogTrapEffect(_TrapEffect):
    defeat_on_no_card: bool = False


@register_effect("deadfall_trap")
class DeadfallTrapEffect(_TrapEffect):
    defeat_on_no_card: bool = True


# ---------------------------------------------------------------------------
# Green chain — Retrieve: True Grit (move 3) / Die Hard (move 4)
# ---------------------------------------------------------------------------


class _RetrieveMoveEffect(CardEffect):
    """You may retrieve a discarded attack card. If an enemy hero in radius is
    adjacent to 3+ obstacles, move up to N spaces."""

    move_distance: int = 3

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                card_action_types=[ActionType.ATTACK],
                prompt="You may retrieve a discarded attack card",
                output_key="retrieved_card",
                is_mandatory=False,
            ),
            RetrieveCardStep(card_key="retrieved_card", active_if_key="retrieved_card"),
            CountStep(
                target_type=TargetType.UNIT,
                output_key="tg_enemy_count",
                filters=[
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                    RangeFilter(max_range=stats.radius),
                    AdjacentToObstaclesFilter(min_count=3),
                ],
            ),
            CheckContextConditionStep(
                input_key="tg_enemy_count", operator=">=", threshold=1, output_key="tg_has_enemy"
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"Move up to {self.move_distance} spaces",
                output_key="tg_move_dest",
                is_mandatory=False,
                active_if_key="tg_has_enemy",
                filters=[
                    RangeFilter(max_range=self.move_distance),
                    MovementPathFilter(range_val=self.move_distance, unit_id=hero.id),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            MoveUnitStep(
                unit_id=hero.id,
                destination_key="tg_move_dest",
                range_val=self.move_distance,
                active_if_key="tg_move_dest",
            ),
        ]


@register_effect("true_grit")
class TrueGritEffect(_RetrieveMoveEffect):
    move_distance: int = 3


@register_effect("die_hard")
class DieHardEffect(_RetrieveMoveEffect):
    move_distance: int = 4


# ---------------------------------------------------------------------------
# Red chain — Melee attacks: High Ground / Elevated Ambush / Peak Precision
# ---------------------------------------------------------------------------


def _obstacle_hero_filters() -> list:
    """Filters testing 'the target is a hero adjacent to 3+ obstacles'."""
    return [UnitTypeFilter(unit_type="HERO"), AdjacentToObstaclesFilter(min_count=3)]


class _BonusAttackEffect(CardEffect):
    """Target a unit adjacent to you. If you target a hero adjacent to 3+
    obstacles, +2 attack."""

    bonus: int = 2

    def _post_attack_steps(self, hero: Hero, card: Card) -> list[GameStep]:
        return []

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps: list[GameStep] = [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target a unit adjacent to you",
                output_key="victim",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                    ImmunityFilter(),
                ],
            ),
            CheckUnitFiltersStep(
                unit_key="victim",
                output_key="ha_qualifies",
                filters=_obstacle_hero_filters(),
            ),
            SetContextFlagStep(key="ha_bonus", value=self.bonus, active_if_key="ha_qualifies"),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                target_id_key="victim",
                damage_bonus_key="ha_bonus",
            ),
        ]
        steps.extend(self._post_attack_steps(hero, card))
        return steps


@register_effect("brynn_high_ground")
class BrynnHighGroundEffect(_BonusAttackEffect):
    pass


@register_effect("elevated_ambush")
class ElevatedAmbushEffect(_BonusAttackEffect):
    pass


@register_effect("peak_precision")
class PeakPrecisionEffect(_BonusAttackEffect):
    """+2 attack AND, after the attack, you may retrieve this card — both only
    when the target is a hero adjacent to 3+ obstacles."""

    def _post_attack_steps(self, hero: Hero, card: Card) -> list[GameStep]:
        return [
            SetContextFlagStep(key="pp_card", value=card.id, active_if_key="ha_qualifies"),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="You may retrieve this card",
                output_key="pp_choice",
                number_options=[1, 0],
                number_labels={1: "Retrieve this card", 0: "No"},
                is_mandatory=False,
                active_if_key="ha_qualifies",
            ),
            CheckContextConditionStep(
                input_key="pp_choice", operator="==", threshold=1, output_key="pp_do"
            ),
            RetrieveCardStep(card_key="pp_card", active_if_key="pp_do"),
        ]


# ---------------------------------------------------------------------------
# Red chain — Splits: Split Attack (repeat adjacent) / Split Throw (repeat range)
# ---------------------------------------------------------------------------


class _SplitEffect(CardEffect):
    """Target a unit in range. If you target a hero adjacent to 3+ obstacles,
    may repeat once on a different unit (adjacent to you / in range)."""

    repeat_adjacent_only: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        repeat_range = 1 if self.repeat_adjacent_only else stats.range
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target a unit in range",
                output_key="victim",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.range),
                    TeamFilter(relation="ENEMY"),
                    ImmunityFilter(),
                ],
            ),
            CheckUnitFiltersStep(
                unit_key="victim",
                output_key="split_qualifies",
                filters=_obstacle_hero_filters(),
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                target_id_key="victim",
            ),
            MayRepeatOnceStep(
                active_if_key="split_qualifies",
                prompt="Repeat the attack on a different unit?",
                steps_template=[
                    SelectStep(
                        target_type=TargetType.UNIT,
                        prompt="Repeat on a different unit",
                        output_key="victim2",
                        is_mandatory=True,
                        filters=[
                            RangeFilter(max_range=repeat_range),
                            TeamFilter(relation="ENEMY"),
                            ImmunityFilter(),
                            ExcludeIdentityFilter(exclude_keys=["victim"]),
                        ],
                    ),
                    AttackSequenceStep(
                        damage=stats.primary_value,
                        range_val=repeat_range,
                        is_ranged=True,
                        target_id_key="victim2",
                    ),
                ],
            ),
        ]


@register_effect("split_attack")
class SplitAttackEffect(_SplitEffect):
    repeat_adjacent_only: bool = True


@register_effect("split_throw")
class SplitThrowEffect(_SplitEffect):
    repeat_adjacent_only: bool = False


# ---------------------------------------------------------------------------
# Untiered — Decoy: move up to two enemies (minion, or obstacle-bound hero) 1 space
# ---------------------------------------------------------------------------


def _decoy_target_filters(radius: int | None) -> list:
    return [
        OrFilter(
            filters=[
                AndFilter(
                    filters=[
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="MINION"),
                        RangeFilter(max_range=radius),
                    ]
                ),
                AndFilter(
                    filters=[
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="HERO"),
                        RangeFilter(max_range=radius),
                        AdjacentToObstaclesFilter(min_count=3),
                    ]
                ),
            ]
        ),
        CanBeMovedByActorFilter(),
    ]


@register_effect("decoy")
class DecoyEffect(CardEffect):
    """Choose up to two times, on different targets — move an enemy minion in
    radius, or an enemy hero in radius adjacent to 3+ obstacles, 1 space."""

    def _decoy_block(
        self, radius: int | None, unit_key: str, dest_key: str, exclude: bool
    ) -> list[GameStep]:
        filters = _decoy_target_filters(radius)
        if exclude:
            filters.append(ExcludeIdentityFilter(exclude_keys=["decoy_unit1"]))
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Move an enemy unit 1 space",
                output_key=unit_key,
                is_mandatory=False,
                filters=filters,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Move it 1 space",
                output_key=dest_key,
                is_mandatory=False,
                active_if_key=unit_key,
                filters=[
                    RangeFilter(max_range=1, origin_key=unit_key),
                    MovementPathFilter(range_val=1, unit_key=unit_key),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            MoveUnitStep(
                unit_key=unit_key,
                destination_key=dest_key,
                range_val=1,
                active_if_key=dest_key,
            ),
        ]

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps = self._decoy_block(stats.radius, "decoy_unit1", "decoy_dest1", exclude=False)
        steps.extend(self._decoy_block(stats.radius, "decoy_unit2", "decoy_dest2", exclude=True))
        return steps


# ---------------------------------------------------------------------------
# Untiered — Familiar Ground: basic ranged attack (adjacent unit, or hero in
# range adjacent to 3+ obstacles)
# ---------------------------------------------------------------------------


@register_effect("familiar_ground")
class FamiliarGroundEffect(CardEffect):
    """Target an adjacent unit or a hero in range adjacent to 3+ obstacles."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target an adjacent unit or a qualifying hero in range",
                output_key="fg_victim",
                is_mandatory=True,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    OrFilter(
                        filters=[
                            RangeFilter(max_range=1),
                            AndFilter(
                                filters=[
                                    UnitTypeFilter(unit_type="HERO"),
                                    RangeFilter(max_range=stats.range),
                                    AdjacentToObstaclesFilter(min_count=3),
                                ]
                            ),
                        ]
                    ),
                ],
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                target_id_key="fg_victim",
            ),
        ]
