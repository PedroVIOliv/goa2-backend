from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models.enums import CardContainerType, TargetType, TokenType
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
    AddContextValueStep,
    AttackSequenceStep,
    CheckContextConditionStep,
    CountStep,
    ForceDiscardStep,
    GainCoinsStep,
    GameStep,
    MoveTokenStep,
    MoveUnitStep,
    PlaceTokenStep,
    PushUnitStep,
    RecordHexStep,
    RemoveTokenStep,
    RemoveUnitStep,
    RetrieveCardStep,
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


@register_effect("master_of_puppets")
class MasterOfPuppetsEffect(CardEffect):
    """Passive: Mortimer may choose five times instead of three times."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return []


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


def _knife_choice_steps(
    prefix: str,
    radius: int,
    *,
    prompt: str,
    active_if_key: str | None = None,
) -> list[GameStep]:
    return [
        SetContextFlagStep(key=f"{prefix}_zombie", value=None),
        SetContextFlagStep(key=f"{prefix}_zombie_dest", value=None),
        SetContextFlagStep(key=f"{prefix}_remove_zombie", value=None),
        _choose_one_step(
            f"{prefix}_choice",
            {
                1: "Move a Zombie token in radius 1 space",
                2: "Remove a Zombie token adjacent to the target for +1 Attack",
            },
            prompt=prompt,
            is_mandatory=False,
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
            radius,
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
            output_key=f"{prefix}_chose_remove",
        ),
        SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Select Zombie token adjacent to the target to remove",
            output_key=f"{prefix}_remove_zombie",
            skip_immunity_filter=True,
            skip_self_filter=True,
            is_mandatory=False,
            active_if_key=f"{prefix}_chose_remove",
            filters=[
                UnitTypeFilter(unit_type="TOKEN"),
                TokenTypeFilter(token_type=TokenType.ZOMBIE),
                RangeFilter(min_range=1, max_range=1, origin_key="knife_target"),
            ],
        ),
        RemoveTokenStep(
            token_key=f"{prefix}_remove_zombie",
            active_if_key=f"{prefix}_remove_zombie",
        ),
        AddContextValueStep(
            key="knife_atk_bonus",
            amount=1,
            active_if_key=f"{prefix}_remove_zombie",
        ),
    ]


def _knife_living_dead_steps(damage: int, radius: int, max_choices: int) -> list[GameStep]:
    steps: list[GameStep] = [
        SetContextFlagStep(key="knife_atk_bonus", value=0),
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select Attack Target",
            output_key="knife_target",
            filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=1)],
            is_mandatory=True,
        ),
    ]
    previous_choice_key: str | None = None
    for i in range(max_choices):
        prefix = f"mortimer_knife_{i}"
        steps.extend(
            _knife_choice_steps(
                prefix,
                radius,
                prompt=f"Choose one (up to {max_choices}, choice {i + 1})",
                active_if_key=previous_choice_key,
            )
        )
        previous_choice_key = f"{prefix}_choice"

    steps.append(
        AttackSequenceStep(
            damage=damage,
            range_val=1,
            target_id_key="knife_target",
            damage_bonus_key="knife_atk_bonus",
        )
    )
    return steps


def _brains_choice_steps(
    prefix: str,
    radius: int,
    *,
    prompt: str,
    active_if_key: str | None = None,
) -> list[GameStep]:
    eligible_count_key = f"{prefix}_eligible_count"
    can_retrieve_key = f"{prefix}_can_retrieve"
    return [
        SetContextFlagStep(key=f"{prefix}_zombie", value=None),
        SetContextFlagStep(key=f"{prefix}_zombie_dest", value=None),
        SetContextFlagStep(key=f"{prefix}_retrieved_card", value=None),
        _choose_one_step(
            f"{prefix}_choice",
            {
                1: "Move a Zombie token in radius 1 space",
                2: "Retrieve a discarded card if an enemy hero in radius is adjacent to a Zombie token",
            },
            prompt=prompt,
            is_mandatory=False,
            active_if_key=active_if_key,
        ),
        # Branch 1: move a zombie token in radius 1 space
        CheckContextConditionStep(
            input_key=f"{prefix}_choice",
            operator="==",
            threshold=1,
            output_key=f"{prefix}_chose_move",
        ),
        _zombie_selection_step(
            f"{prefix}_zombie",
            radius,
            active_if_key=f"{prefix}_chose_move",
        ),
        *_zombie_move_steps(
            zombie_key=f"{prefix}_zombie",
            destination_key=f"{prefix}_zombie_dest",
            active_if_key=f"{prefix}_chose_move",
        ),
        # Branch 2: retrieve a discarded card iff an enemy hero in radius is
        # adjacent to a Zombie token. Counts under the same gate so a SKIP on
        # this choice cannot accidentally surface the retrieve prompt.
        CheckContextConditionStep(
            input_key=f"{prefix}_choice",
            operator="==",
            threshold=2,
            output_key=f"{prefix}_chose_retrieve",
        ),
        CountStep(
            target_type=TargetType.UNIT,
            output_key=eligible_count_key,
            active_if_key=f"{prefix}_chose_retrieve",
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=radius),
                CountMatchFilter(
                    min_count=1,
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
        CheckContextConditionStep(
            input_key=eligible_count_key,
            operator=">",
            threshold=0,
            output_key=can_retrieve_key,
        ),
        SelectStep(
            target_type=TargetType.CARD,
            prompt="Select a discarded card to retrieve",
            output_key=f"{prefix}_retrieved_card",
            card_container=CardContainerType.DISCARD,
            is_mandatory=False,
            active_if_key=can_retrieve_key,
        ),
        RetrieveCardStep(
            card_key=f"{prefix}_retrieved_card",
            active_if_key=f"{prefix}_retrieved_card",
        ),
    ]


def _brains_steps(damage: int, radius: int, max_choices: int) -> list[GameStep]:
    steps: list[GameStep] = [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select Attack Target",
            output_key="brains_target",
            filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=1)],
            is_mandatory=True,
        ),
    ]
    previous_choice_key: str | None = None
    for i in range(max_choices):
        prefix = f"mortimer_brains_{i}"
        steps.extend(
            _brains_choice_steps(
                prefix,
                radius,
                prompt=f"Choose one (up to {max_choices}, choice {i + 1})",
                active_if_key=previous_choice_key,
            )
        )
        previous_choice_key = f"{prefix}_choice"

    steps.append(
        AttackSequenceStep(
            damage=damage,
            range_val=1,
            target_id_key="brains_target",
        )
    )
    return steps


def _dead_choice_steps(
    prefix: str,
    radius: int,
    *,
    prompt: str,
    is_mandatory: bool,
    active_if_key: str | None = None,
    excluded_hero_keys: list[str] | None = None,
) -> list[GameStep]:
    hero_key = f"{prefix}_hero"
    discard_excluded_keys = ["dead_target", *(excluded_hero_keys or [])]
    return [
        SetContextFlagStep(key=f"{prefix}_zombie", value=None),
        SetContextFlagStep(key=f"{prefix}_zombie_dest", value=None),
        SetContextFlagStep(key=hero_key, value=None),
        _choose_one_step(
            f"{prefix}_choice",
            {
                1: "Move a Zombie token in radius 1 space",
                2: "An enemy hero in radius adjacent to a Zombie token discards a card",
            },
            prompt=prompt,
            is_mandatory=is_mandatory,
            active_if_key=active_if_key,
        ),
        # Branch 1: move a zombie token in radius 1 space.
        CheckContextConditionStep(
            input_key=f"{prefix}_choice",
            operator="==",
            threshold=1,
            output_key=f"{prefix}_chose_move",
        ),
        _zombie_selection_step(
            f"{prefix}_zombie",
            radius,
            active_if_key=f"{prefix}_chose_move",
        ),
        *_zombie_move_steps(
            zombie_key=f"{prefix}_zombie",
            destination_key=f"{prefix}_zombie_dest",
            active_if_key=f"{prefix}_chose_move",
        ),
        # Branch 2: an eligible enemy hero discards a card.
        # The attack target ("dead_target") is always excluded so the
        # "another enemy hero" wording holds. ``excluded_hero_keys`` carries
        # the per-iteration "each enemy hero only once" constraint.
        CheckContextConditionStep(
            input_key=f"{prefix}_choice",
            operator="==",
            threshold=2,
            output_key=f"{prefix}_chose_discard",
        ),
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select an enemy hero adjacent to a Zombie token to discard a card",
            output_key=hero_key,
            is_mandatory=False,
            active_if_key=f"{prefix}_chose_discard",
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=radius),
                CountMatchFilter(
                    min_count=1,
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
                ExcludeIdentityFilter(
                    exclude_self=False,
                    exclude_keys=discard_excluded_keys,
                ),
            ],
        ),
        ForceDiscardStep(victim_key=hero_key, active_if_key=hero_key),
    ]


def _dead_steps(
    damage: int,
    radius: int,
    max_choices: int,
    *,
    enforce_once_per_hero: bool,
) -> list[GameStep]:
    steps: list[GameStep] = [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select Attack Target",
            output_key="dead_target",
            filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=1)],
            is_mandatory=True,
        ),
        AttackSequenceStep(
            damage=damage,
            range_val=1,
            target_id_key="dead_target",
        ),
    ]
    previous_choice_key: str | None = None
    prior_hero_keys: list[str] = []
    for i in range(max_choices):
        prefix = f"mortimer_dead_{i}"
        steps.extend(
            _dead_choice_steps(
                prefix,
                radius,
                prompt=(
                    f"Choose one (up to {max_choices}, choice {i + 1})"
                    if max_choices > 1
                    else "Choose one"
                ),
                # T1 ("Choose one") forces a choice; T2/T3 ("up to N times")
                # are optional so the player can stop early.
                is_mandatory=(max_choices == 1),
                active_if_key=previous_choice_key,
                excluded_hero_keys=list(prior_hero_keys) if enforce_once_per_hero else None,
            )
        )
        previous_choice_key = f"{prefix}_choice"
        if enforce_once_per_hero:
            prior_hero_keys.append(f"{prefix}_hero")
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
        assert stats.radius is not None, "awaken card requires a radius"
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


@register_effect("knife_of_the_living_dead")
class KnifeOfTheLivingDeadEffect(CardEffect):
    """Adjacent attack; before it, move Zombies or remove adjacent Zombies for +Attack."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        assert stats.radius is not None, "knife_of_the_living_dead card requires a radius"
        return _knife_living_dead_steps(stats.primary_value, stats.radius, _choice_limit(hero, 3))


@register_effect("braaains")
class BraaainsEffect(CardEffect):
    """Adjacent attack; before it, move Zombies or retrieve a card if a Zombie pins an enemy hero."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        assert stats.radius is not None, "braaains card requires a radius"
        return _brains_steps(stats.primary_value, stats.radius, _choice_limit(hero, 2))


@register_effect("braaaaaaaaains")
class BraaaaaaaaainsEffect(CardEffect):
    """Tier III Brains: up to three choices (five with Master of Puppets)."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        assert stats.radius is not None, "braaaaaaaaains card requires a radius"
        return _brains_steps(stats.primary_value, stats.radius, _choice_limit(hero, 3))


@register_effect("crawling_dead")
class CrawlingDeadEffect(CardEffect):
    """Adjacent attack; after it, choose one — move a Zombie or force a hero to discard."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        assert stats.radius is not None, "crawling_dead card requires a radius"
        return _dead_steps(
            stats.primary_value,
            stats.radius,
            max_choices=1,
            enforce_once_per_hero=False,
        )


@register_effect("walking_dead")
class WalkingDeadEffect(CardEffect):
    """Tier II Dead: up to two post-attack choices; each enemy hero may discard at most once."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        assert stats.radius is not None, "walking_dead card requires a radius"
        return _dead_steps(
            stats.primary_value,
            stats.radius,
            max_choices=_choice_limit(hero, 2),
            enforce_once_per_hero=True,
        )


@register_effect("racing_dead")
class RacingDeadEffect(CardEffect):
    """Tier III Dead: up to three (five with Master of Puppets); once-per-hero discard."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        assert stats.radius is not None, "racing_dead card requires a radius"
        return _dead_steps(
            stats.primary_value,
            stats.radius,
            max_choices=_choice_limit(hero, 3),
            enforce_once_per_hero=True,
        )


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
