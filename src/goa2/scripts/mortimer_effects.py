from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models.enums import TargetType, TokenType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.filters_composite import AndFilter, CountMatchFilter, OrFilter
from goa2.engine.filters_hex import (
    MovementPathFilter,
    ObstacleFilter,
    RangeFilter,
    SpawnPointFilter,
)
from goa2.engine.filters_units import (
    ExcludeIdentityFilter,
    TeamFilter,
    TokenTypeFilter,
    UnitTypeFilter,
)
from goa2.engine.steps import (
    CheckContextConditionStep,
    GainCoinsStep,
    GameStep,
    MoveTokenStep,
    MoveUnitStep,
    PlaceTokenStep,
    PushUnitStep,
    RecordHexStep,
    RemoveUnitStep,
    SelectStep,
    SetContextFlagStep,
    SwapUnitsStep,
)

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


def _choose_one_step(
    output_key: str,
    number_labels: dict[int, str],
    *,
    prompt: str = "Choose one",
    is_mandatory: bool = True,
    active_if_key: str | None = None,
) -> SelectStep:
    return SelectStep(
        target_type=TargetType.NUMBER,
        prompt=prompt,
        output_key=output_key,
        number_options=[1, 2],
        number_labels=number_labels,
        is_mandatory=is_mandatory,
        active_if_key=active_if_key,
    )


def _zombie_selection_step(output_key: str, range_val: int, *, active_if_key: str) -> SelectStep:
    return SelectStep(
        target_type=TargetType.UNIT_OR_TOKEN,
        prompt="Select a Zombie token",
        output_key=output_key,
        skip_immunity_filter=True,
        skip_self_filter=True,
        filters=[
            UnitTypeFilter(unit_type="TOKEN"),
            TokenTypeFilter(token_type=TokenType.ZOMBIE),
            RangeFilter(max_range=range_val),
        ],
        active_if_key=active_if_key,
        is_mandatory=False,
    )


def _zombie_move_steps(
    *,
    zombie_key: str,
    destination_key: str,
    active_if_key: str,
    allow_zero: bool = False,
    is_mandatory: bool = False,
) -> list[GameStep]:
    destination_filters = [
        ObstacleFilter(is_obstacle=False),
        MovementPathFilter(range_val=1, unit_key=zombie_key),
        RangeFilter(max_range=1, origin_key=zombie_key),
    ]
    if allow_zero:
        destination_filters = [
            OrFilter(
                filters=[
                    RangeFilter(max_range=0, origin_key=zombie_key),
                    AndFilter(filters=destination_filters),
                ]
            )
        ]

    return [
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Select Zombie destination",
            output_key=destination_key,
            filters=destination_filters,
            active_if_key=active_if_key,
            is_mandatory=is_mandatory,
        ),
        MoveTokenStep(
            token_key=zombie_key,
            destination_key=destination_key,
            range_val=1,
            active_if_key=destination_key,
        ),
    ]


def _has_master_of_puppets(hero: Hero) -> bool:
    return (
        hero.level >= 8
        and hero.ultimate_card is not None
        and hero.ultimate_card.id == "master_of_puppets"
    )


def _choice_limit(hero: Hero, base_limit: int) -> int:
    if base_limit == 3 and _has_master_of_puppets(hero):
        return 5
    return base_limit


def _stage_dive_choice_steps(
    prefix: str,
    range_val: int,
    *,
    prompt: str = "Choose one",
    is_mandatory: bool = True,
    active_if_key: str | None = None,
) -> list[GameStep]:
    return [
        SetContextFlagStep(key=f"{prefix}_zombie", value=None),
        SetContextFlagStep(key=f"{prefix}_zombie_dest", value=None),
        SetContextFlagStep(key=f"{prefix}_swap_zombie", value=None),
        _choose_one_step(
            f"{prefix}_choice",
            {
                1: "Move a Zombie token in range 1 space",
                2: "Swap with a Zombie token in range",
            },
            prompt=prompt,
            is_mandatory=is_mandatory,
            active_if_key=active_if_key,
        ),
        CheckContextConditionStep(
            input_key=f"{prefix}_choice",
            operator="==",
            threshold=1,
            output_key=f"{prefix}_chose_move",
        ),
        _zombie_selection_step(
            f"{prefix}_zombie",
            range_val,
            active_if_key=f"{prefix}_chose_move",
        ),
        *_zombie_move_steps(
            zombie_key=f"{prefix}_zombie",
            destination_key=f"{prefix}_zombie_dest",
            active_if_key=f"{prefix}_chose_move",
        ),
        CheckContextConditionStep(
            input_key=f"{prefix}_choice",
            operator="==",
            threshold=2,
            output_key=f"{prefix}_chose_swap",
        ),
        _zombie_selection_step(
            f"{prefix}_swap_zombie",
            range_val,
            active_if_key=f"{prefix}_chose_swap",
        ),
        SwapUnitsStep(
            unit_a_key=f"{prefix}_hero",
            unit_b_key=f"{prefix}_swap_zombie",
            active_if_key=f"{prefix}_swap_zombie",
        ),
    ]


def _stage_dive_repeat_steps(hero: Hero, range_val: int, max_choices: int) -> list[GameStep]:
    steps: list[GameStep] = []
    previous_choice_key: str | None = None
    for i in range(max_choices):
        prefix = f"mortimer_crowd_{i}"
        steps.append(SetContextFlagStep(key=f"{prefix}_hero", value=str(hero.id)))
        steps.extend(
            _stage_dive_choice_steps(
                prefix,
                range_val,
                prompt=f"Choose one (up to {max_choices}, choice {i + 1})",
                is_mandatory=False,
                active_if_key=previous_choice_key,
            )
        )
        previous_choice_key = f"{prefix}_choice"
    return steps


def _horde_choice_steps(
    prefix: str,
    range_val: int,
    *,
    prompt: str = "Choose one",
    is_mandatory: bool = True,
    active_if_key: str | None = None,
) -> list[GameStep]:
    replace_key = f"{prefix}_replace_minion"
    replace_hex_key = f"{prefix}_replace_hex"

    return [
        SetContextFlagStep(key=f"{prefix}_zombie", value=None),
        SetContextFlagStep(key=f"{prefix}_zombie_dest", value=None),
        SetContextFlagStep(key=replace_key, value=None),
        SetContextFlagStep(key=replace_hex_key, value=None),
        _choose_one_step(
            f"{prefix}_choice",
            {
                1: "Move a Zombie token in range 1 space",
                2: "Replace an enemy minion adjacent to two or more Zombie tokens",
            },
            prompt=prompt,
            is_mandatory=is_mandatory,
            active_if_key=active_if_key,
        ),
        CheckContextConditionStep(
            input_key=f"{prefix}_choice",
            operator="==",
            threshold=1,
            output_key=f"{prefix}_chose_move",
        ),
        _zombie_selection_step(
            f"{prefix}_zombie",
            range_val,
            active_if_key=f"{prefix}_chose_move",
        ),
        *_zombie_move_steps(
            zombie_key=f"{prefix}_zombie",
            destination_key=f"{prefix}_zombie_dest",
            active_if_key=f"{prefix}_chose_move",
        ),
        CheckContextConditionStep(
            input_key=f"{prefix}_choice",
            operator="==",
            threshold=2,
            output_key=f"{prefix}_chose_replace",
        ),
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select enemy minion to replace with a Zombie token",
            output_key=replace_key,
            is_mandatory=False,
            active_if_key=f"{prefix}_chose_replace",
            skip_if_key="mortimer_horde_replaced",
            filters=[
                UnitTypeFilter(unit_type="MINION"),
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=range_val),
                CountMatchFilter(
                    min_count=2,
                    include_tokens=True,
                    sub_filters=[
                        UnitTypeFilter(unit_type="TOKEN"),
                        TokenTypeFilter(token_type=TokenType.ZOMBIE),
                        RangeFilter(
                            min_range=1,
                            max_range=1,
                            origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY,
                        ),
                    ],
                ),
            ],
        ),
        RecordHexStep(
            unit_key=replace_key,
            output_key=replace_hex_key,
            active_if_key=replace_key,
        ),
        RemoveUnitStep(unit_key=replace_key, active_if_key=replace_key),
        PlaceTokenStep(
            token_type=TokenType.ZOMBIE,
            hex_key=replace_hex_key,
            active_if_key=replace_hex_key,
        ),
        SetContextFlagStep(
            key="mortimer_horde_replaced",
            value=True,
            active_if_key=replace_key,
        ),
    ]


def _horde_repeat_steps(hero: Hero, range_val: int, max_choices: int) -> list[GameStep]:
    steps: list[GameStep] = [SetContextFlagStep(key="mortimer_horde_replaced", value=None)]
    previous_choice_key: str | None = None
    for i in range(max_choices):
        prefix = f"mortimer_horde_{i}"
        steps.extend(
            _horde_choice_steps(
                prefix,
                range_val,
                prompt=f"Choose one (up to {max_choices}, choice {i + 1})",
                is_mandatory=False,
                active_if_key=previous_choice_key,
            )
        )
        previous_choice_key = f"{prefix}_choice"
    return steps


def _corpse_slam_choice_steps(
    prefix: str,
    range_val: int,
    *,
    prompt: str = "Choose one",
    is_mandatory: bool = True,
    active_if_key: str | None = None,
    push_after_zombie: bool = True,
    gain_coin_after_zombie: bool = False,
) -> list[GameStep]:
    steps: list[GameStep] = [
        SetContextFlagStep(key=f"{prefix}_zombie", value=None),
        SetContextFlagStep(key=f"{prefix}_zombie_dest", value=None),
        SetContextFlagStep(key=f"{prefix}_push_target", value=None),
        _choose_one_step(
            f"{prefix}_choice",
            {
                1: (
                    "Move a Zombie token in range up to 1 space; it may push adjacent"
                    if push_after_zombie
                    else "Move a Zombie token in range up to 1 space and gain 1 coin"
                ),
                2: "Move 1 space",
            },
            prompt=prompt,
            is_mandatory=is_mandatory,
            active_if_key=active_if_key,
        ),
        CheckContextConditionStep(
            input_key=f"{prefix}_choice",
            operator="==",
            threshold=1,
            output_key=f"{prefix}_chose_zombie",
        ),
        _zombie_selection_step(
            f"{prefix}_zombie",
            range_val,
            active_if_key=f"{prefix}_chose_zombie",
        ),
        *_zombie_move_steps(
            zombie_key=f"{prefix}_zombie",
            destination_key=f"{prefix}_zombie_dest",
            active_if_key=f"{prefix}_chose_zombie",
            allow_zero=True,
            is_mandatory=True,
        ),
    ]

    if push_after_zombie:
        steps.extend(
            [
                SelectStep(
                    target_type=TargetType.UNIT_OR_TOKEN,
                    prompt="Select adjacent unit or token to push",
                    output_key=f"{prefix}_push_target",
                    skip_immunity_filter=True,
                    skip_self_filter=True,
                    filters=[RangeFilter(min_range=1, max_range=1, origin_key=f"{prefix}_zombie")],
                    active_if_key=f"{prefix}_zombie",
                    is_mandatory=False,
                ),
                PushUnitStep(
                    target_key=f"{prefix}_push_target",
                    source_key=f"{prefix}_zombie",
                    distance=1,
                    active_if_key=f"{prefix}_push_target",
                ),
            ]
        )

    if gain_coin_after_zombie:
        steps.append(
            GainCoinsStep(
                hero_key=f"{prefix}_hero",
                amount=1,
                active_if_key=f"{prefix}_zombie_dest",
            )
        )

    steps.extend(
        [
            CheckContextConditionStep(
                input_key=f"{prefix}_choice",
                operator="==",
                threshold=2,
                output_key=f"{prefix}_chose_move",
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select Movement Destination (Range 1)",
                output_key=f"{prefix}_self_dest",
                filters=[
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=1, unit_key=f"{prefix}_hero"),
                ],
                active_if_key=f"{prefix}_chose_move",
                is_mandatory=False,
            ),
            MoveUnitStep(
                unit_key=f"{prefix}_hero",
                range_val=1,
                destination_key=f"{prefix}_self_dest",
                active_if_key=f"{prefix}_self_dest",
                is_mandatory=False,
            ),
        ]
    )
    return steps


def _corpse_slam_repeat_steps(
    hero: Hero,
    range_val: int,
    max_choices: int,
    *,
    push_after_zombie: bool,
    gain_coin_after_zombie: bool,
) -> list[GameStep]:
    steps: list[GameStep] = []
    previous_choice_key: str | None = None
    for i in range(max_choices):
        prefix = f"mortimer_blue_{i}"
        steps.append(SetContextFlagStep(key=f"{prefix}_hero", value=str(hero.id)))
        steps.extend(
            _corpse_slam_choice_steps(
                prefix,
                range_val,
                prompt=f"Choose one (up to {max_choices}, choice {i + 1})",
                is_mandatory=False,
                active_if_key=previous_choice_key,
                push_after_zombie=push_after_zombie,
                gain_coin_after_zombie=gain_coin_after_zombie,
            )
        )
        previous_choice_key = f"{prefix}_choice"
    return steps


@register_effect("awaken")
class AwakenEffect(CardEffect):
    """Place up to 4 Zombie tokens adjacent to you or into spawn points in radius."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _awaken_placement_steps(stats.radius)


@register_effect("stage_dive")
class StageDiveEffect(CardEffect):
    """Choose one: move a Zombie token in range 1 space, or swap with one in range."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SetContextFlagStep(key="stage_dive_hero", value=str(hero.id)),
            *_stage_dive_choice_steps("stage_dive", stats.range),
        ]


@register_effect("crowd_drift")
class CrowdDriftEffect(CardEffect):
    """Choose up to two times: move a Zombie token, or swap with one in range."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _stage_dive_repeat_steps(hero, stats.range, _choice_limit(hero, 2))


@register_effect("crowd_surf")
class CrowdSurfEffect(CardEffect):
    """Choose up to three times, or five with Master of Puppets."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _stage_dive_repeat_steps(hero, stats.range, _choice_limit(hero, 3))


@register_effect("gathering_horde")
class GatheringHordeEffect(CardEffect):
    """Choose up to two times: move a Zombie, or once replace a surrounded enemy minion."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _horde_repeat_steps(hero, stats.range, _choice_limit(hero, 2))


@register_effect("army_of_darkness")
class ArmyOfDarknessEffect(CardEffect):
    """Choose up to three times, or five with Master of Puppets."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _horde_repeat_steps(hero, stats.range, _choice_limit(hero, 3))


@register_effect("corpse_slam")
class CorpseSlamEffect(CardEffect):
    """Choose one: move a Zombie token that may push adjacent, or move 1 space."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SetContextFlagStep(key="corpse_slam_hero", value=str(hero.id)),
            *_corpse_slam_choice_steps("corpse_slam", stats.range),
        ]


@register_effect("morbid_mosh")
class MorbidMoshEffect(CardEffect):
    """Choose up to two times: Zombie move/push or Mortimer move."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _corpse_slam_repeat_steps(
            hero,
            stats.range,
            _choice_limit(hero, 2),
            push_after_zombie=True,
            gain_coin_after_zombie=False,
        )


@register_effect("macabre_mayhem")
class MacabreMayhemEffect(CardEffect):
    """Choose up to three times, or five with Master of Puppets."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _corpse_slam_repeat_steps(
            hero,
            stats.range,
            _choice_limit(hero, 3),
            push_after_zombie=True,
            gain_coin_after_zombie=False,
        )


@register_effect("robbing_zombies")
class RobbingZombiesEffect(CardEffect):
    """Choose up to two times: Zombie move plus coin, or Mortimer move."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _corpse_slam_repeat_steps(
            hero,
            stats.range,
            _choice_limit(hero, 2),
            push_after_zombie=False,
            gain_coin_after_zombie=True,
        )


@register_effect("stalking_scalpers")
class StalkingScalpersEffect(CardEffect):
    """Choose up to three times, or five with Master of Puppets."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _corpse_slam_repeat_steps(
            hero,
            stats.range,
            _choice_limit(hero, 3),
            push_after_zombie=False,
            gain_coin_after_zombie=True,
        )
