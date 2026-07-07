"""NebKher card effects — critical-infrastructure cards.

NebKher is an illusion/topology hero. This module implements the five effects
that ride on new engine primitives (see
docs/superpowers/plans/2026-07-07-nebkher-tdd-paths.md):

- crack_in_reality / shift_reality  -> topology split (TopologyService)
- mind_grip                         -> PerformCardActionStep (enemy prev slot,
                                       Illusion substitution, marker skip)
- diabolical_laughter               -> LaughStep + up-to-3 menu +
                                       SwapResolvedCardsStep
- what_the_hell_are_you (ultimate)  -> AFTER_LAUGH passive

The delegable families (Imbue Doubt line, Illusion placement line,
Phantasmal line) are implemented separately.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models import (
    CardContainerType,
    CardState,
    TokenType,
)
from goa2.domain.models.effect import DurationType, EffectScope, EffectType, Shape
from goa2.domain.models.enums import PassiveTrigger, TargetType
from goa2.engine.effects import CardEffect, PassiveConfig, register_effect
from goa2.engine.filters import (
    HasPreviousSlotCardFilter,
    ObstacleFilter,
    RangeFilter,
    TeamFilter,
    TokenTypeFilter,
    UnitTypeFilter,
)
from goa2.engine.steps import (
    CheckContextConditionStep,
    CollectUnitsStep,
    CreateEffectStep,
    DefeatUnitStep,
    ForceDiscardOrDefeatStep,
    ForEachStep,
    GameStep,
    LaughStep,
    MayRepeatNTimesStep,
    PerformCardActionStep,
    PlaceTokenStep,
    SelectStep,
    SwapResolvedCardsStep,
    SwapUnitsStep,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


# =============================================================================
# CRACK IN REALITY / SHIFT REALITY
# "Split the board into two sides with a straight line of spaces drawn
#  through your space. This turn: …cannot interact… as if they did not exist."
# =============================================================================

_AXES: list[tuple[int, str]] = [(1, "q"), (2, "r"), (3, "s")]


@register_effect("crack_in_reality")
class CrackInRealityEffect(CardEffect):
    """Tier-2 split: the two sides cannot interact with each other; the line
    itself bridges both. The line is fixed at cast time."""

    topology_effect_type: EffectType = EffectType.TOPOLOGY_SPLIT

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        hero_hex = state.get_position(str(hero.id))
        if hero_hex is None:
            return []

        steps: list[GameStep] = [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose the line of spaces drawn through your space",
                output_key="reality_axis",
                number_options=[idx for idx, _ in _AXES],
                number_labels={
                    idx: f"Line along the {axis}-axis (through your space)" for idx, axis in _AXES
                },
                is_mandatory=True,
            )
        ]
        for idx, axis in _AXES:
            steps.append(
                CheckContextConditionStep(
                    input_key="reality_axis",
                    operator="==",
                    threshold=idx,
                    output_key=f"reality_axis_{axis}",
                )
            )
            steps.append(
                CreateEffectStep(
                    effect_type=self.topology_effect_type,
                    scope=EffectScope(shape=Shape.GLOBAL, origin_id=str(hero.id)),
                    duration=DurationType.THIS_TURN,
                    is_active=True,
                    split_axis=axis,
                    split_value=getattr(hero_hex, axis),
                    # Fallback anchor only — the live source position takes
                    # precedence for Shift Reality's isolation (S6).
                    isolated_hex=hero_hex,
                    active_if_key=f"reality_axis_{axis}",
                )
            )
        return steps


@register_effect("shift_reality")
class ShiftRealityEffect(CrackInRealityEffect):
    """Tier-3 split: additionally, units on either side cannot interact with
    NebKher himself (mutual isolation); only units on the line can."""

    topology_effect_type: EffectType = EffectType.TOPOLOGY_ISOLATION


# =============================================================================
# MIND GRIP (gold basic skill, ranged 5)
# "Choose one —
#  • Perform an action on the card in the previous turn slot of an enemy hero
#    in range; if you would place any tokens this way, place Illusion tokens
#    instead; skip giving markers.
#  • Defeat a minion adjacent to you."
# =============================================================================


@register_effect("mind_grip")
class MindGripEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Mind Grip — choose one",
                output_key="mg_choice",
                number_options=[1, 2],
                number_labels={
                    1: "Perform an action on an enemy hero's previous card",
                    2: "Defeat a minion adjacent to you",
                },
                is_mandatory=True,
            ),
            # Bullet 1: perform an action from the enemy's previous turn slot.
            CheckContextConditionStep(
                input_key="mg_choice", operator="==", threshold=1, output_key="mg_perform"
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero in range with a card in their previous turn slot",
                output_key="mg_target_hero",
                is_mandatory=True,
                active_if_key="mg_perform",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range or 0),
                    HasPreviousSlotCardFilter(),
                ],
            ),
            PerformCardActionStep(
                card_owner_key="mg_target_hero",
                previous_slot=True,
                hero_id=str(hero.id),
                token_type_override=TokenType.ILLUSION,
                skip_markers=True,
                active_if_key="mg_target_hero",
            ),
            # Bullet 2: defeat an adjacent minion.
            CheckContextConditionStep(
                input_key="mg_choice", operator="==", threshold=2, output_key="mg_defeat"
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select a minion adjacent to you to defeat",
                output_key="mg_minion",
                is_mandatory=True,
                active_if_key="mg_defeat",
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                ],
            ),
            DefeatUnitStep(
                victim_key="mg_minion",
                killer_id=str(hero.id),
                active_if_key="mg_minion",
            ),
        ]


# =============================================================================
# DIABOLICAL LAUGHTER (silver basic skill, radius 4)
# "Laugh diabolically; if you do, choose up to three times —
#  • Swap with an Illusion token in radius.
#  • Place an Illusion token in an adjacent space.
#  • Swap two resolved cards of an enemy hero in radius, without canceling
#    active effects."
# =============================================================================


def _laughter_menu_steps(hero_id: str, radius: int) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.NUMBER,
            prompt="Diabolical Laughter — choose an option",
            output_key="dl_pick",
            number_options=[1, 2, 3],
            number_labels={
                1: "Swap with an Illusion token in radius",
                2: "Place an Illusion token in an adjacent space",
                3: "Swap two resolved cards of an enemy hero in radius",
            },
            is_mandatory=True,
        ),
        # Bullet 1: swap self with an Illusion token in radius.
        CheckContextConditionStep(
            input_key="dl_pick", operator="==", threshold=1, output_key="dl_b1"
        ),
        SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Select an Illusion token in radius",
            output_key="dl_swap_token",
            is_mandatory=True,
            active_if_key="dl_b1",
            filters=[
                UnitTypeFilter(unit_type="TOKEN"),
                TokenTypeFilter(token_type=TokenType.ILLUSION),
                RangeFilter(max_range=radius),
            ],
        ),
        SwapUnitsStep(
            unit_a_id=hero_id,
            unit_b_key="dl_swap_token",
            active_if_key="dl_swap_token",
        ),
        # Bullet 2: place an Illusion token in an adjacent empty space.
        CheckContextConditionStep(
            input_key="dl_pick", operator="==", threshold=2, output_key="dl_b2"
        ),
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Select an adjacent space for the Illusion token",
            output_key="dl_place_hex",
            is_mandatory=True,
            active_if_key="dl_b2",
            filters=[
                RangeFilter(max_range=1),
                ObstacleFilter(is_obstacle=False),
            ],
        ),
        PlaceTokenStep(
            token_type=TokenType.ILLUSION,
            hex_key="dl_place_hex",
            active_if_key="dl_place_hex",
        ),
        # Bullet 3: swap two resolved cards of an enemy hero in radius.
        CheckContextConditionStep(
            input_key="dl_pick", operator="==", threshold=3, output_key="dl_b3"
        ),
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select an enemy hero in radius with two resolved cards",
            output_key="dl_victim",
            is_mandatory=True,
            active_if_key="dl_b3",
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=radius),
                _two_resolved_cards_filter(),
            ],
        ),
        SelectStep(
            target_type=TargetType.CARD,
            prompt="Select the first resolved card to swap",
            output_key="dl_card_a",
            card_container=CardContainerType.PLAYED,
            card_states=[CardState.RESOLVED],
            context_hero_id_key="dl_victim",
            is_mandatory=True,
            active_if_key="dl_victim",
        ),
        SelectStep(
            target_type=TargetType.CARD,
            prompt="Select the second resolved card to swap",
            output_key="dl_card_b",
            card_container=CardContainerType.PLAYED,
            card_states=[CardState.RESOLVED],
            exclude_card_id_keys=["dl_card_a"],
            context_hero_id_key="dl_victim",
            is_mandatory=True,
            active_if_key="dl_card_a",
        ),
        SwapResolvedCardsStep(
            hero_key="dl_victim",
            card_a_key="dl_card_a",
            card_b_key="dl_card_b",
            active_if_key="dl_card_b",
        ),
    ]


def _two_resolved_cards_filter():
    from goa2.engine.filters import CardsInContainerFilter

    return CardsInContainerFilter(container=CardContainerType.PLAYED, min_cards=2)


@register_effect("diabolical_laughter")
class DiabolicalLaughterEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        return [
            LaughStep(output_key="dl_laughed"),
            MayRepeatNTimesStep(
                max_repeats=3,
                prompt="Diabolical Laughter: choose an option?",
                steps_template=_laughter_menu_steps(str(hero.id), radius),
                active_if_key="dl_laughed",
            ),
        ]


# =============================================================================
# ULTIMATE — WHAT THE HELL ARE YOU? (passive, radius 5)
# "Each time after you laugh diabolically as part of performing an action,
#  all enemy heroes in radius discard a card, or are defeated."
# =============================================================================


@register_effect("what_the_hell_are_you")
class WhatTheHellAreYouEffect(CardEffect):
    def get_passive_config(self) -> PassiveConfig:
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_LAUGH,
            uses_per_turn=0,  # every laugh
            is_optional=False,  # "all enemy heroes … discard, or are defeated"
        )

    def get_passive_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict,
    ) -> list[GameStep]:
        if trigger != PassiveTrigger.AFTER_LAUGH:
            return []
        from goa2.domain.types import UnitID
        from goa2.engine.stats import compute_card_stats

        stats = compute_card_stats(state, UnitID(str(hero.id)), card)
        radius = stats.radius or 0
        return [
            CollectUnitsStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=radius),
                ],
                output_key="wthau_victims",
            ),
            ForEachStep(
                list_key="wthau_victims",
                item_key="wthau_victim",
                steps_template=[ForceDiscardOrDefeatStep(victim_key="wthau_victim")],
            ),
        ]
