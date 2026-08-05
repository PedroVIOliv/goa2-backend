"""Wuk card effects.

Wuk is a Tree-token-centric hero. Tree tokens (TokenType.TREE) are standard
tokens: supply 3, persist end-of-round, block movement (not ranged line of
sight). See docs/superpowers/specs/2026-06-27-wuk-hero-effects-design.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models import CardContainerType, TargetType, TokenType
from goa2.domain.models.effect import DurationType, EffectScope, EffectType, Shape
from goa2.domain.models.enums import PassiveTrigger
from goa2.engine.effects import CardEffect, PassiveConfig, register_effect
from goa2.engine.filters_cards import CardsInContainerFilter
from goa2.engine.filters_composite import CountMatchFilter, OrFilter
from goa2.engine.filters_geometry import BetweenHexesFilter
from goa2.engine.filters_hex import ObstacleFilter, RangeFilter
from goa2.engine.filters_units import (
    ExcludeIdentityFilter,
    TeamFilter,
    TokenTypeFilter,
    UnitTypeFilter,
)
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CollectUnitsStep,
    CreateEffectStep,
    DefeatUnitStep,
    ForceDiscardOrDefeatStep,
    ForEachStep,
    GameStep,
    MayRepeatNTimesStep,
    MayRepeatOnceStep,
    MoveSequenceStep,
    PlaceTokenStep,
    PlaceUnitStep,
    RecordHexStep,
    RemoveTokenStep,
    RetrieveCardStep,
    SelectStep,
    SwapUnitsStep,
)


def _adjacent_to_tree_filter() -> CountMatchFilter:
    """Candidate unit passes if at least one Tree token sits adjacent to it."""
    return CountMatchFilter(
        include_tokens=True,
        min_count=1,
        sub_filters=[
            TokenTypeFilter(token_type=TokenType.TREE),
            RangeFilter(max_range=1, origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY),
        ],
    )


if TYPE_CHECKING:
    from typing import Any

    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


# ---------------------------------------------------------------------------
# Group A — Throw: "Place a token, or an enemy unit, adjacent to you into a
# space in range."
# ---------------------------------------------------------------------------
def _throw_steps(range_val: int) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Select a token or adjacent enemy unit to throw",
            output_key="throw_target",
            is_mandatory=True,
            filters=[
                RangeFilter(max_range=1),
                OrFilter(
                    filters=[
                        UnitTypeFilter(unit_type="TOKEN"),
                        TeamFilter(relation="ENEMY"),
                    ]
                ),
            ],
        ),
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Select a space in range",
            output_key="throw_dest",
            is_mandatory=True,
            filters=[
                RangeFilter(max_range=range_val),
                ObstacleFilter(is_obstacle=False),
            ],
        ),
        PlaceUnitStep(
            unit_key="throw_target",
            destination_key="throw_dest",
            is_mandatory=True,
        ),
    ]


@register_effect("toss_away")
class TossAwayEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _throw_steps(stats.range)


@register_effect("mighty_throw")
class MightyThrowEffect(TossAwayEffect):
    pass


@register_effect("monstrous_throw")
class MonstrousThrowEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps = _throw_steps(stats.range)
        return [*steps, MayRepeatOnceStep(steps_template=_throw_steps(stats.range))]


# ---------------------------------------------------------------------------
# Group B — Canopy swap: "Choose one — Swap with a Tree token in radius. /
# Swap a friendly unit in radius with a Tree token in radius."
# ---------------------------------------------------------------------------
def _tree_in_radius_select(output_key: str, radius: int, active_if_key: str | None) -> SelectStep:
    return SelectStep(
        target_type=TargetType.UNIT_OR_TOKEN,
        prompt="Select a Tree token in radius",
        output_key=output_key,
        is_mandatory=True,
        active_if_key=active_if_key,
        filters=[
            UnitTypeFilter(unit_type="TOKEN"),
            TokenTypeFilter(token_type=TokenType.TREE),
            RangeFilter(max_range=radius),
        ],
    )


def _canopy_choice_steps(hero_id: str, radius: int) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.NUMBER,
            prompt="Choose one",
            output_key="canopy_choice",
            number_options=[1, 2],
            number_labels={
                1: "Swap with a Tree token",
                2: "Swap a friendly unit with a Tree token",
            },
        ),
        # Branch 1: swap yourself with a Tree token.
        CheckContextConditionStep(
            input_key="canopy_choice", operator="==", threshold=1, output_key="canopy_self"
        ),
        _tree_in_radius_select("canopy_tree_self", radius, active_if_key="canopy_self"),
        SwapUnitsStep(
            unit_a_id=hero_id,
            unit_b_key="canopy_tree_self",
            active_if_key="canopy_tree_self",
        ),
        # Branch 2: swap a friendly unit with a Tree token.
        CheckContextConditionStep(
            input_key="canopy_choice", operator="==", threshold=2, output_key="canopy_ally"
        ),
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select a friendly unit in radius",
            output_key="canopy_ally_unit",
            is_mandatory=True,
            active_if_key="canopy_ally",
            filters=[
                TeamFilter(relation="FRIENDLY"),
                RangeFilter(max_range=radius),
            ],
        ),
        _tree_in_radius_select("canopy_tree_ally", radius, active_if_key="canopy_ally"),
        SwapUnitsStep(
            unit_a_key="canopy_ally_unit",
            unit_b_key="canopy_tree_ally",
            active_if_key="canopy_tree_ally",
        ),
    ]


@register_effect("into_the_canopy")
class IntoTheCanopyEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _canopy_choice_steps(str(hero.id), stats.radius or 0)


@register_effect("treetop_ride")
class TreetopRideEffect(CardEffect):
    """Choose up to two times."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            MayRepeatNTimesStep(
                max_repeats=2,
                prompt="Resolve a Canopy swap?",
                steps_template=_canopy_choice_steps(str(hero.id), stats.radius or 0),
            )
        ]


# ---------------------------------------------------------------------------
# Group C — Dominance: "This round: Up to N enemy minions adjacent to you do
# not count toward the minion total during minion battle, regardless of
# immunity." No targeting; reduction is computed at minion-battle resolution.
# ---------------------------------------------------------------------------
def _dominance_steps(hero_id: str, cap: int) -> list[GameStep]:
    return [
        CreateEffectStep(
            effect_type=EffectType.MINION_BATTLE_EXCLUSION,
            scope=EffectScope(shape=Shape.POINT, origin_id=hero_id),
            # PASSIVE, not THIS_ROUND: EndPhaseStep expires THIS_ROUND effects
            # *before* the minion battle, which would make the exclusion a no-op.
            # The effect is card-bound, so it is cleaned up when the card is
            # retrieved in EndPhaseCleanupStep (which runs after the battle) —
            # giving it exactly a one-round lifetime that covers the battle.
            duration=DurationType.PASSIVE,
            max_value=cap,
            is_active=True,
        )
    ]


@register_effect("claim_dominance")
class ClaimDominanceEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _dominance_steps(str(hero.id), 1)


@register_effect("assert_dominance")
class AssertDominanceEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _dominance_steps(str(hero.id), 2)


# ---------------------------------------------------------------------------
# Group D — Retrieve: "Remove a Tree token in radius. [retrieve a discarded
# card / a friendly hero in radius retrieves]." Removing a Tree token is a
# required cost: no tree in radius -> the mandatory select aborts the action.
# ---------------------------------------------------------------------------
def _remove_tree_cost(radius: int) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Remove a Tree token in radius",
            output_key="retrieve_tree",
            is_mandatory=True,
            filters=[
                UnitTypeFilter(unit_type="TOKEN"),
                TokenTypeFilter(token_type=TokenType.TREE),
                RangeFilter(max_range=radius),
            ],
        ),
        RemoveTokenStep(token_key="retrieve_tree"),
    ]


def _self_retrieve_steps(active_if_key: str | None = None) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.CARD,
            card_container=CardContainerType.DISCARD,
            prompt="You may retrieve a discarded card",
            output_key="self_retrieve_card",
            is_mandatory=False,
            active_if_key=active_if_key,
        ),
        RetrieveCardStep(card_key="self_retrieve_card", active_if_key="self_retrieve_card"),
    ]


def _friendly_retrieve_steps(radius: int, active_if_key: str | None = None) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select a friendly hero in radius with a discarded card",
            output_key="friendly_retrieve_ally",
            is_mandatory=False,
            active_if_key=active_if_key,
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="FRIENDLY"),
                RangeFilter(max_range=radius),
                CardsInContainerFilter(container=CardContainerType.DISCARD, min_cards=1),
            ],
        ),
        SelectStep(
            target_type=TargetType.CARD,
            card_container=CardContainerType.DISCARD,
            prompt="Select a card to retrieve",
            output_key="friendly_retrieve_card",
            context_hero_id_key="friendly_retrieve_ally",
            override_player_id_key="friendly_retrieve_ally",
            is_mandatory=True,
            active_if_key="friendly_retrieve_ally",
        ),
        RetrieveCardStep(
            card_key="friendly_retrieve_card",
            hero_key="friendly_retrieve_ally",
            active_if_key="friendly_retrieve_card",
        ),
    ]


@register_effect("gifts_of_nature")
class GiftsOfNatureEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _remove_tree_cost(stats.radius or 0) + _self_retrieve_steps()


@register_effect("tree_of_plenty")
class TreeOfPlentyEffect(CardEffect):
    """Choose one — self retrieve OR a friendly hero retrieves."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        return [
            *_remove_tree_cost(radius),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="retrieve_choice",
                number_options=[1, 2],
                number_labels={1: "You retrieve", 2: "A friendly hero retrieves"},
            ),
            CheckContextConditionStep(
                input_key="retrieve_choice",
                operator="==",
                threshold=1,
                output_key="retrieve_self",
            ),
            CheckContextConditionStep(
                input_key="retrieve_choice",
                operator="==",
                threshold=2,
                output_key="retrieve_friendly",
            ),
            *_self_retrieve_steps(active_if_key="retrieve_self"),
            *_friendly_retrieve_steps(radius, active_if_key="retrieve_friendly"),
        ]


@register_effect("abundance")
class AbundanceEffect(CardEffect):
    """Choose one or both — self retrieve and/or a friendly hero retrieves."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        return _remove_tree_cost(radius) + _self_retrieve_steps() + _friendly_retrieve_steps(radius)


# ---------------------------------------------------------------------------
# Group E — Nature's weapon: "Choose one [Champion: one or both, on different
# targets] — Target a hero adjacent to you. / Target a unit in range adjacent
# to a Tree token." Ranged ATTACK cards.
# ---------------------------------------------------------------------------
def _nw_mode1_select(
    output_key: str,
    *,
    mandatory: bool,
    active_if_key: str | None,
    exclude_keys: list[str] | None = None,
) -> SelectStep:
    filters: list = [
        UnitTypeFilter(unit_type="HERO"),
        TeamFilter(relation="ENEMY"),
        RangeFilter(max_range=1),
    ]
    if exclude_keys:
        filters.append(ExcludeIdentityFilter(exclude_keys=exclude_keys))
    return SelectStep(
        target_type=TargetType.UNIT,
        prompt="Target an adjacent enemy hero",
        output_key=output_key,
        is_mandatory=mandatory,
        active_if_key=active_if_key,
        filters=filters,
    )


def _nw_mode2_select(
    output_key: str,
    range_val: int,
    *,
    mandatory: bool,
    active_if_key: str | None,
    exclude_keys: list[str] | None = None,
) -> SelectStep:
    filters: list = [
        TeamFilter(relation="ENEMY"),
        RangeFilter(max_range=range_val),
        _adjacent_to_tree_filter(),
    ]
    if exclude_keys:
        filters.append(ExcludeIdentityFilter(exclude_keys=exclude_keys))
    return SelectStep(
        target_type=TargetType.UNIT,
        prompt="Target a unit in range adjacent to a Tree token",
        output_key=output_key,
        is_mandatory=mandatory,
        active_if_key=active_if_key,
        filters=filters,
    )


def _nw_attack(target_key: str, damage: int, range_val: int) -> AttackSequenceStep:
    return AttackSequenceStep(
        damage=damage,
        range_val=range_val,
        is_ranged=True,
        target_id_key=target_key,
        active_if_key=target_key,
    )


def _nature_weapon_choose_one(damage: int, range_val: int) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.NUMBER,
            prompt="Choose one",
            output_key="nw_choice",
            number_options=[1, 2],
            number_labels={1: "Adjacent enemy hero", 2: "Unit in range adjacent to a Tree token"},
        ),
        CheckContextConditionStep(
            input_key="nw_choice", operator="==", threshold=1, output_key="nw_mode1"
        ),
        CheckContextConditionStep(
            input_key="nw_choice", operator="==", threshold=2, output_key="nw_mode2"
        ),
        _nw_mode1_select("nw_target1", mandatory=True, active_if_key="nw_mode1"),
        _nw_attack("nw_target1", damage, 1),
        _nw_mode2_select("nw_target2", range_val, mandatory=True, active_if_key="nw_mode2"),
        _nw_attack("nw_target2", damage, range_val),
    ]


class _NatureWeaponEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _nature_weapon_choose_one(stats.primary_value, stats.range)


@register_effect("natures_protector")
class NaturesProtectorEffect(_NatureWeaponEffect):
    pass


@register_effect("natures_guardian")
class NaturesGuardianEffect(_NatureWeaponEffect):
    pass


@register_effect("natures_champion")
class NaturesChampionEffect(CardEffect):
    """Choose one, or both, on different targets — in either order.

    The player first picks which mode to resolve first, then each attack is
    offered optionally (different targets enforced via ExcludeIdentityFilter),
    so either mode's board effects can land first."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        damage = stats.primary_value
        range_val = stats.range
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose which attack to resolve first",
                output_key="champ_order",
                number_options=[1, 2],
                number_labels={
                    1: "Adjacent enemy hero first",
                    2: "Unit in range adjacent to a Tree token first",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="champ_order", operator="==", threshold=1, output_key="champ_hero_first"
            ),
            CheckContextConditionStep(
                input_key="champ_order", operator="==", threshold=2, output_key="champ_tree_first"
            ),
            # PATH hero first: mode 1 then mode 2 (different target). Uses
            # path-local keys so the other path's attacks (which gate on their
            # own target keys) never fire here.
            _nw_mode1_select("champ_h1", mandatory=False, active_if_key="champ_hero_first"),
            _nw_attack("champ_h1", damage, 1),
            _nw_mode2_select(
                "champ_h2",
                range_val,
                mandatory=False,
                active_if_key="champ_hero_first",
                exclude_keys=["champ_h1"],
            ),
            _nw_attack("champ_h2", damage, range_val),
            # PATH tree first: mode 2 then mode 1 (different target).
            _nw_mode2_select(
                "champ_t2",
                range_val,
                mandatory=False,
                active_if_key="champ_tree_first",
            ),
            _nw_attack("champ_t2", damage, range_val),
            _nw_mode1_select(
                "champ_t1",
                mandatory=False,
                active_if_key="champ_tree_first",
                exclude_keys=["champ_t2"],
            ),
            _nw_attack("champ_t1", damage, 1),
        ]


# ---------------------------------------------------------------------------
# Group F — Mystic Saplings (Silver): "Place up to 3 Tree tokens in radius;
# Tree tokens are not removed at the end of round." (Trees persist by default.)
# ---------------------------------------------------------------------------
@register_effect("mystic_saplings")
class MysticSaplingsEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        steps: list[GameStep] = []
        for i in range(3):
            hex_key = f"sapling_hex_{i}"
            steps.append(
                SelectStep(
                    target_type=TargetType.HEX,
                    prompt="Place a Tree token in radius",
                    output_key=hex_key,
                    is_mandatory=False,
                    active_if_key=f"sapling_hex_{i - 1}" if i > 0 else None,
                    filters=[
                        RangeFilter(max_range=radius),
                        ObstacleFilter(is_obstacle=False),
                    ],
                )
            )
            steps.append(
                PlaceTokenStep(
                    token_type=TokenType.TREE,
                    hex_key=hex_key,
                    active_if_key=hex_key,
                )
            )
        return steps


# ---------------------------------------------------------------------------
# Group G — Tree Slam (Gold): "Choose one — Target a minion adjacent to you. /
# Remove a Tree token adjacent to you. Target a unit in range."
# ---------------------------------------------------------------------------
@register_effect("tree_slam")
class TreeSlamEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        damage = stats.primary_value
        range_val = stats.range
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="slam_choice",
                number_options=[1, 2],
                number_labels={
                    1: "Target an adjacent minion",
                    2: "Remove an adjacent Tree token, then target a unit in range",
                },
            ),
            # Mode 1: attack an adjacent enemy minion.
            CheckContextConditionStep(
                input_key="slam_choice", operator="==", threshold=1, output_key="slam_mode1"
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target an adjacent enemy minion",
                output_key="slam_minion",
                is_mandatory=True,
                active_if_key="slam_mode1",
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                ],
            ),
            _nw_attack("slam_minion", damage, 1),
            # Mode 2: remove an adjacent Tree token (cost), then attack any unit in range.
            CheckContextConditionStep(
                input_key="slam_choice", operator="==", threshold=2, output_key="slam_mode2"
            ),
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Remove an adjacent Tree token",
                output_key="slam_tree",
                is_mandatory=True,
                active_if_key="slam_mode2",
                filters=[
                    UnitTypeFilter(unit_type="TOKEN"),
                    TokenTypeFilter(token_type=TokenType.TREE),
                    RangeFilter(max_range=1),
                ],
            ),
            RemoveTokenStep(token_key="slam_tree", active_if_key="slam_tree"),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target a unit in range",
                output_key="slam_target",
                is_mandatory=True,
                active_if_key="slam_mode2",
                filters=[
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=range_val),
                ],
            ),
            _nw_attack("slam_target", damage, range_val),
        ]


# ---------------------------------------------------------------------------
# Group H — March of Nature (Ultimate, passive): "Each time after you resolve
# a card, you may place a Tree token in radius."
# ---------------------------------------------------------------------------
@register_effect("march_of_nature")
class MarchOfNatureEffect(CardEffect):
    def get_passive_config(self) -> PassiveConfig | None:
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_RESOLVE_CARD,
            uses_per_turn=0,  # each card resolved
            is_optional=True,
            prompt="March of Nature: Place a Tree token in radius?",
        )

    def get_passive_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict[Any, Any],
    ) -> list[GameStep]:
        if trigger != PassiveTrigger.AFTER_RESOLVE_CARD:
            return []
        radius = card.radius_value or 0
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Place a Tree token in radius",
                output_key="march_tree_hex",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=radius),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceTokenStep(
                token_type=TokenType.TREE,
                hex_key="march_tree_hex",
                active_if_key="march_tree_hex",
            ),
        ]


# ---------------------------------------------------------------------------
# Group I — Trample: "If you move in a straight line: You may ignore obstacles;
# each enemy hero you moved through discards a card, or is defeated; defeat up
# to N minions you moved through."
#
# The player first chooses ordinary movement or the straight-line Trample mode.
# This preserves ordinary path choice while making the direct Trample ray
# explicit for obstacle crossing and crossed-unit effects.
# ---------------------------------------------------------------------------
def _crossed_filter() -> BetweenHexesFilter:
    return BetweenHexesFilter(from_hex_key="move_origin", to_hex_key="move_dest")


def _trample_steps(hero_id: str, move_range: int, max_minions: int) -> list[GameStep]:
    steps: list[GameStep] = [
        RecordHexStep(unit_id=hero_id, output_key="move_origin"),
        SelectStep(
            target_type=TargetType.NUMBER,
            prompt="Choose how to move",
            output_key="trample_mode",
            number_options=[1, 2],
            number_labels={1: "Normal movement", 2: "Straight-line Trample"},
            is_mandatory=True,
        ),
        CheckContextConditionStep(
            input_key="trample_mode",
            operator="==",
            threshold=1,
            output_key="chose_normal_movement",
        ),
        CheckContextConditionStep(
            input_key="trample_mode",
            operator="==",
            threshold=2,
            output_key="chose_trample",
        ),
        MoveSequenceStep(
            unit_id=hero_id,
            range_val=move_range,
            destination_key="move_dest",
            active_if_key="chose_normal_movement",
        ),
        MoveSequenceStep(
            unit_id=hero_id,
            range_val=move_range,
            destination_key="move_dest",
            pass_through_obstacles=True,
            force_straight_line=True,
            active_if_key="chose_trample",
        ),
        # Each enemy hero moved through discards a card, or is defeated — this is
        # mandatory for ALL of them, not a player choice, so collect the whole
        # set automatically. Immune heroes are skipped (ImmunityFilter
        # auto-added by CollectUnitsStep).
        CollectUnitsStep(
            target_type=TargetType.UNIT,
            output_key="trample_heroes",
            active_if_key="chose_trample",
            filters=[
                _crossed_filter(),
                TeamFilter(relation="ENEMY"),
                UnitTypeFilter(unit_type="HERO"),
            ],
        ),
        ForEachStep(
            list_key="trample_heroes",
            item_key="trample_hero",
            steps_template=[ForceDiscardOrDefeatStep(victim_key="trample_hero")],
        ),
    ]

    # Up to N crossed minions, defeated via SEPARATE sequential selects so that
    # ImmunityFilter is re-evaluated each time — defeating a support minion can
    # strip an adjacent heavy's immunity and make it selectable next.
    for i in range(max_minions):
        minion_key = f"trample_minion_{i}"
        steps.append(
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Defeat an enemy minion you moved through",
                output_key=minion_key,
                is_mandatory=False,
                active_if_key="chose_trample",
                filters=[
                    _crossed_filter(),
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="MINION"),
                    ExcludeIdentityFilter(exclude_keys=[f"trample_minion_{j}" for j in range(i)]),
                ],
            )
        )
        steps.append(DefeatUnitStep(victim_key=minion_key, active_if_key=minion_key))

    return steps


@register_effect("trample")
class TrampleEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _trample_steps(str(hero.id), stats.primary_value, max_minions=1)


@register_effect("angry_stampede")
class AngryStampedeEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _trample_steps(str(hero.id), stats.primary_value, max_minions=2)
