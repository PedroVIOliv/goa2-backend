"""Trinkets card effects.

Trinkets is a board-entity-origin hero: most effects are written from the
Turret's position rather than from Trinkets. The Turret is a unique non-unit,
non-token BoardEntity (see PlaceTurretStep/RemoveTurretStep) that counts as
an obstacle. Only one Turret ever exists; placing it again repositions it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import (
    CardContainerType,
    StatType,
    TargetType,
    TokenType,
)
from goa2.engine.effects import CardEffect, StatAura, register_effect
from goa2.engine.filters_geometry import InStraightLineFilter
from goa2.engine.filters_hex import MovementPathFilter, ObstacleFilter, RangeFilter
from goa2.engine.filters_units import (
    ExcludeIdentityFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CheckDistanceStep,
    CheckUnitFiltersStep,
    CreateEffectStep,
    DefeatUnitStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    ForEachStep,
    GameStep,
    MayRepeatNTimesStep,
    MoveUnitStep,
    MultiSelectStep,
    PlaceTokenStep,
    PlaceTurretStep,
    PlaceUnitStep,
    RecordTargetStep,
    RemoveTurretStep,
    RetrieveCardStep,
    SelectStep,
    SetContextFlagStep,
    SwapUnitsStep,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats

TURRET_ID = "trinkets_turret"


# =============================================================================
# RED CARDS — Cannons (dual-origin) and Turret-adjacent attacks
# =============================================================================


class _DualOriginCannonEffect(CardEffect):
    """
    Shared logic for Makeshift Minigun / Gatling Gun / Supercharged Cannon:
    "Target a unit in range of both you and the Turret. If the target is in a
    straight line from you, and in a straight line from the Turret, gain
    +N Attack."
    """

    straight_line_bonus: int = 2

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        range_val = stats.range or 1
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select a unit in range of both you and the Turret",
                output_key="cannon_target",
                is_mandatory=True,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=range_val),
                    RangeFilter(max_range=range_val, origin_id=TURRET_ID),
                ],
            ),
            CheckUnitFiltersStep(
                unit_key="cannon_target",
                filters=[
                    InStraightLineFilter(),
                    InStraightLineFilter(origin_id=TURRET_ID),
                ],
                output_key="cannon_aligned",
            ),
            SetContextFlagStep(
                key="cannon_bonus",
                value=self.straight_line_bonus,
                active_if_key="cannon_aligned",
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=range_val,
                is_ranged=True,
                target_id_key="cannon_target",
                damage_bonus_key="cannon_bonus",
            ),
        ]


@register_effect("makeshift_minigun")
class MakeshiftMinigunEffect(_DualOriginCannonEffect):
    """Tier I cannon: +2 Attack when aligned with both origins."""

    straight_line_bonus = 2


@register_effect("gatling_gun")
class GatlingGunEffect(_DualOriginCannonEffect):
    """Tier II cannon: +2 Attack when aligned with both origins."""

    straight_line_bonus = 2


@register_effect("supercharged_cannon")
class SuperchargedCannonEffect(_DualOriginCannonEffect):
    """Tier III cannon: +3 Attack when aligned with both origins."""

    straight_line_bonus = 3


def _turret_adjacent_attack_steps(damage: int, range_val: int) -> list[GameStep]:
    """Attack a unit in card range that is also adjacent to the Turret.

    Records each victim so repeats can exclude all previous targets
    ("may repeat ... on different enemy units").
    """
    return [
        AttackSequenceStep(
            damage=damage,
            range_val=range_val,
            is_ranged=True,
            target_filters=[
                RangeFilter(max_range=1, origin_id=TURRET_ID),
                ExcludeIdentityFilter(exclude_keys=["turret_attack_victims"]),
            ],
        ),
        RecordTargetStep(input_key="victim_id", output_list_key="turret_attack_victims"),
    ]


class _TurretAdjacentAttackEffect(CardEffect):
    """
    Shared logic for Steam Discharge / Flame Belcher:
    "Target a unit in range adjacent to the Turret.
    May repeat once / up to two times on different enemy units."
    """

    max_repeats: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        range_val = stats.range or 1
        return [
            *_turret_adjacent_attack_steps(stats.primary_value, range_val),
            MayRepeatNTimesStep(
                max_repeats=self.max_repeats,
                prompt="Repeat the attack on a different enemy unit?",
                steps_template=_turret_adjacent_attack_steps(stats.primary_value, range_val),
            ),
        ]


@register_effect("steam_discharge")
class SteamDischargeEffect(_TurretAdjacentAttackEffect):
    """Tier II: may repeat once."""

    max_repeats = 1


@register_effect("flame_belcher")
class FlameBelcherEffect(_TurretAdjacentAttackEffect):
    """Tier III: may repeat up to two times."""

    max_repeats = 2


# =============================================================================
# BLUE CARDS — Barriers and Disruptors
# =============================================================================


class _DeployableBarrierEffect(CardEffect):
    """
    Shared logic for Deployable Barrier / Deployable Bastion:
    "Place up to N Barrier tokens in radius, with at least one of them
    adjacent to the Turret; you and friendly heroes gain +1 Defense for
    each Barrier token they are adjacent to."

    The first token must be adjacent to the Turret; later placements are
    gated on the previous one so skipping ends the sequence (preserving the
    at-least-one-adjacent constraint). Each token carries its own
    token-bound ADJACENT defense aura, removed with the token.
    """

    token_count: int = 2

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        steps: list[GameStep] = []
        for i in range(self.token_count):
            hex_key = f"barrier_hex_{i}"
            token_key = f"barrier_token_{i}"
            filters = [
                RangeFilter(max_range=radius),
                ObstacleFilter(is_obstacle=False),
            ]
            if i == 0:
                prompt = "Select a space adjacent to the Turret for the first Barrier token"
                filters.append(RangeFilter(max_range=1, origin_id=TURRET_ID))
            else:
                prompt = "Select a space in radius for another Barrier token"
            steps.extend(
                [
                    SelectStep(
                        target_type=TargetType.HEX,
                        prompt=prompt,
                        output_key=hex_key,
                        is_mandatory=False,
                        active_if_key=f"barrier_hex_{i - 1}" if i > 0 else None,
                        filters=filters,
                    ),
                    PlaceTokenStep(
                        token_type=TokenType.BARRIER,
                        hex_key=hex_key,
                        output_key=token_key,
                        active_if_key=hex_key,
                    ),
                    CreateEffectStep(
                        effect_type=EffectType.AREA_STAT_MODIFIER,
                        scope=EffectScope(
                            shape=Shape.ADJACENT,
                            affects=AffectsFilter.SELF_AND_FRIENDLY_HEROES,
                        ),
                        origin_id_key=token_key,
                        is_token_effect=True,
                        duration=DurationType.PASSIVE,
                        stat_type=StatType.DEFENSE,
                        stat_value=1,
                        active_if_key=token_key,
                    ),
                ]
            )
        return steps


@register_effect("deployable_barrier")
class DeployableBarrierEffect(_DeployableBarrierEffect):
    """Tier II: up to 2 Barrier tokens."""

    token_count = 2


@register_effect("deployable_bastion")
class DeployableBastionEffect(_DeployableBarrierEffect):
    """Tier III: up to 3 Barrier tokens."""

    token_count = 3


class _DisruptorEffect(CardEffect):
    """
    Shared logic for Disruptor Jolt / Pulse / Grid:
    "This turn: Before any enemy hero in radius of the Turret performs a
    primary action, that hero discards a card[, or is defeated]; if they
    discard a card, deactivate this effect."

    Creates a PRE_ACTION_DISCARD effect anchored to the Turret. The trigger
    itself is resolved by ResolvePreActionDiscardStep, scheduled by
    ResolveCardStep before every primary action.
    """

    discard_or_defeat: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.PRE_ACTION_DISCARD,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=TURRET_ID,
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                discard_or_defeat=self.discard_or_defeat,
            ),
        ]


@register_effect("disruptor_jolt")
class DisruptorJoltEffect(_DisruptorEffect):
    """Tier I: discards a card, if able."""

    discard_or_defeat = False


@register_effect("disruptor_pulse")
class DisruptorPulseEffect(_DisruptorEffect):
    """Tier II: discards a card, if able."""

    discard_or_defeat = False


@register_effect("disruptor_grid")
class DisruptorGridEffect(_DisruptorEffect):
    """Tier III: discards a card, or is defeated."""

    discard_or_defeat = True


# =============================================================================
# GREEN CARDS — Self-destruct and Design (swap/place) families
# =============================================================================


class _SelfDestructEffect(CardEffect):
    """
    Shared logic for Self-Destruct / Emergency Protocol:
    "Up to two enemy heroes in radius of the Turret discard a card,
    if able [or are defeated]. Remove the Turret."
    """

    discard_or_defeat: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        discard_step: GameStep
        if self.discard_or_defeat:
            discard_step = ForceDiscardOrDefeatStep(victim_key="self_destruct_victim")
        else:
            discard_step = ForceDiscardStep(victim_key="self_destruct_victim")
        return [
            MultiSelectStep(
                target_type=TargetType.UNIT,
                prompt="Select up to 2 enemy heroes in radius of the Turret",
                output_key="self_destruct_victims",
                max_selections=2,
                min_selections=0,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius or 0, origin_id=TURRET_ID),
                ],
            ),
            ForEachStep(
                list_key="self_destruct_victims",
                item_key="self_destruct_victim",
                steps_template=[discard_step],
            ),
            RemoveTurretStep(is_mandatory=True),
        ]


@register_effect("self_destruct")
class SelfDestructEffect(_SelfDestructEffect):
    """Tier II: discard a card, if able."""

    discard_or_defeat = False


@register_effect("emergency_protocol")
class EmergencyProtocolEffect(_SelfDestructEffect):
    """Tier III: discard a card, or be defeated."""

    discard_or_defeat = True


def _design_gate_step(hero_id: str, radius: int) -> GameStep:
    """Gate: 'If you are in radius of the Turret' (topology-aware distance)."""
    return CheckDistanceStep(
        unit_a_id=hero_id,
        unit_b_id=TURRET_ID,
        operator="<=",
        threshold=radius,
        output_key="design_in_radius",
    )


def _design_swap_steps(hero_id: str, radius: int, active_if: str) -> list[GameStep]:
    """Swap with a unit or token in radius of the Turret."""
    return [
        SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Select a unit or token in radius of the Turret to swap with",
            output_key="design_swap_target",
            is_mandatory=True,
            active_if_key=active_if,
            filters=[RangeFilter(max_range=radius, origin_id=TURRET_ID)],
        ),
        SwapUnitsStep(
            unit_a_id=hero_id,
            unit_b_key="design_swap_target",
            active_if_key="design_swap_target",
        ),
    ]


@register_effect("early_prototype")
class EarlyPrototypeEffect(CardEffect):
    """
    "If you are in radius of the Turret, swap with a unit or a token in
    radius of the Turret, then remove the Turret."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        return [
            _design_gate_step(str(hero.id), radius),
            *_design_swap_steps(str(hero.id), radius, active_if="design_in_radius"),
            RemoveTurretStep(active_if_key="design_swap_target"),
        ]


@register_effect("updated_design")
class UpdatedDesignEffect(CardEffect):
    """
    "If you are in radius of the Turret, swap with a unit or a token in
    radius of the Turret."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        return [
            _design_gate_step(str(hero.id), radius),
            *_design_swap_steps(str(hero.id), radius, active_if="design_in_radius"),
        ]


@register_effect("perfected_design")
class PerfectedDesignEffect(CardEffect):
    """
    "If you are in radius of the Turret, Choose one —
    • Swap with a unit or a token in radius of the Turret.
    • Place yourself into a space in radius of the Turret."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        return [
            _design_gate_step(str(hero.id), radius),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="design_choice",
                number_options=[1, 2],
                number_labels={
                    1: "Swap with a unit or a token in radius of the Turret",
                    2: "Place yourself into a space in radius of the Turret",
                },
                is_mandatory=True,
                active_if_key="design_in_radius",
            ),
            CheckContextConditionStep(
                input_key="design_choice",
                operator="==",
                threshold=1,
                output_key="design_choice_swap",
            ),
            *_design_swap_steps(str(hero.id), radius, active_if="design_choice_swap"),
            CheckContextConditionStep(
                input_key="design_choice",
                operator="==",
                threshold=2,
                output_key="design_choice_place",
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space in radius of the Turret",
                output_key="design_place_hex",
                is_mandatory=True,
                active_if_key="design_choice_place",
                filters=[
                    RangeFilter(max_range=radius, origin_id=TURRET_ID),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceUnitStep(
                unit_id=str(hero.id),
                destination_key="design_place_hex",
                active_if_key="design_place_hex",
            ),
        ]


# =============================================================================
# UNTIERED CARDS — Turret setup
# =============================================================================


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
                    MovementPathFilter(range_val=3),
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


@register_effect("rapid_redeployment")
class RapidRedeploymentEffect(CardEffect):
    """
    Choose one:
    - Move up to 3 spaces and place the Turret into a space adjacent to you;
      it counts as an obstacle.
    - Defeat a minion adjacent to you.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="redeploy_choice",
                number_options=[1, 2],
                number_labels={
                    1: "Move up to 3 spaces and place the Turret adjacent to you",
                    2: "Defeat a minion adjacent to you",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="redeploy_choice",
                operator="==",
                threshold=1,
                output_key="redeploy_deploy",
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select destination (up to 3 spaces)",
                output_key="redeploy_move_hex",
                active_if_key="redeploy_deploy",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=3),
                    ObstacleFilter(is_obstacle=False),
                    MovementPathFilter(range_val=3),
                ],
            ),
            MoveUnitStep(
                unit_id=str(hero.id),
                destination_key="redeploy_move_hex",
                range_val=3,
                active_if_key="redeploy_move_hex",
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select an adjacent space for the Turret",
                output_key="redeploy_turret_hex",
                active_if_key="redeploy_deploy",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceTurretStep(
                hex_key="redeploy_turret_hex",
                owner_id=str(hero.id),
                active_if_key="redeploy_turret_hex",
                output_key="redeploy_turret_id",
            ),
            CheckContextConditionStep(
                input_key="redeploy_choice",
                operator="==",
                threshold=2,
                output_key="redeploy_defeat",
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select a minion adjacent to you to defeat",
                output_key="redeploy_minion",
                active_if_key="redeploy_defeat",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                ],
            ),
            DefeatUnitStep(
                victim_key="redeploy_minion",
                killer_id=str(hero.id),
                active_if_key="redeploy_minion",
            ),
        ]


# =============================================================================
# ULTIMATE
# =============================================================================


@register_effect("unlimited_firepower")
class UnlimitedFirepowerEffect(CardEffect):
    """Ultimate passive: Gain +1 Range and +1 Radius."""

    def get_stat_auras(self) -> list[StatAura]:
        return [
            StatAura(stat_type=StatType.RANGE, flat_bonus=1),
            StatAura(stat_type=StatType.RADIUS, flat_bonus=1),
        ]
