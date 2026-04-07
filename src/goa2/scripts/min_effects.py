from __future__ import annotations
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from goa2.domain.models.effect import (
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import CardColor, CardState, TokenType
from goa2.engine.effects import CardEffect, CardEffectRegistry, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CreateEffectStep,
    ForceDiscardOrDefeatStep,
    ForEachStep,
    GameStep,
    MultiSelectStep,
    MoveUnitStep,
    PlaceTokenStep,
    PushUnitStep,
    RemoveTokenStep,
    SelectStep,
    SetContextFlagStep,
    SwapUnitsStep,
    TargetType,
)
from goa2.engine.filters import (
    AdjacencyToContextFilter,
    ExcludeIdentityFilter,
    MovementPathFilter,
    ObstacleFilter,
    RangeFilter,
    TeamFilter,
    TokenTypeFilter,
    UnitTypeFilter,
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


# =============================================================================
# RED CARDS — Stances
# =============================================================================


@register_effect("crane_stance")
class CraneStanceEffect(CardEffect):
    """
    Target a unit adjacent to you.
    After the attack: Push an enemy unit adjacent to you up to 3 spaces.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # After attack: optional push adjacent enemy up to 3
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an adjacent enemy to push (optional)",
                output_key="push_target_id",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance",
                output_key="push_distance",
                number_options=[0, 1, 2, 3],
                number_labels={0: "No Push", 1: "Push 1", 2: "Push 2", 3: "Push 3"},
                active_if_key="push_target_id",
            ),
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
                is_mandatory=False,
            ),
        ]


@register_effect("tiger_stance")
class TigerStanceEffect(CardEffect):
    """
    Target a unit adjacent to you.
    After the attack: You may move 1 space to a space adjacent to the target.
    Push an enemy unit adjacent to you up to 3 spaces.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # After attack: optional move 1 to hex adjacent to target
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Move to a space adjacent to the target (optional)",
                output_key="move_hex",
                is_mandatory=False,
                filters=[
                    MovementPathFilter(range_val=1, unit_id=str(hero.id)),
                    AdjacencyToContextFilter(target_key="defender_id"),
                ],
            ),
            MoveUnitStep(
                unit_id=str(hero.id),
                destination_key="move_hex",
                range_val=1,
                active_if_key="move_hex",
            ),
            # Push adjacent enemy up to 3
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an adjacent enemy to push (optional)",
                output_key="push_target_id",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance",
                output_key="push_distance",
                number_options=[0, 1, 2, 3],
                number_labels={0: "No Push", 1: "Push 1", 2: "Push 2", 3: "Push 3"},
                active_if_key="push_target_id",
            ),
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
                is_mandatory=False,
            ),
        ]


@register_effect("dragon_stance")
class DragonStanceEffect(CardEffect):
    """
    Target a unit adjacent to you.
    After the attack: You may move 1 or 2 spaces to a space adjacent to the target.
    Push an enemy unit adjacent to you up to 3 spaces.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # After attack: optional move 1-2 to hex adjacent to target
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Move to a space adjacent to the target (optional)",
                output_key="move_hex",
                is_mandatory=False,
                filters=[
                    MovementPathFilter(range_val=2, unit_id=str(hero.id)),
                    AdjacencyToContextFilter(target_key="defender_id"),
                ],
            ),
            MoveUnitStep(
                unit_id=str(hero.id),
                destination_key="move_hex",
                range_val=2,
                active_if_key="move_hex",
            ),
            # Push adjacent enemy up to 3
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an adjacent enemy to push (optional)",
                output_key="push_target_id",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance",
                output_key="push_distance",
                number_options=[0, 1, 2, 3],
                number_labels={0: "No Push", 1: "Push 1", 2: "Push 2", 3: "Push 3"},
                active_if_key="push_target_id",
            ),
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
                is_mandatory=False,
            ),
        ]


@register_effect("viper_stance")
class ViperStanceEffect(CardEffect):
    """
    Target a unit adjacent to you.
    After the attack: You may swap with a Smoke bomb in radius.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # After attack: optional swap with smoke bomb in radius
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select a Smoke Bomb to swap with (optional)",
                output_key="swap_token_id",
                is_mandatory=False,
                skip_immunity_filter=True,
                filters=[
                    RangeFilter(max_range=stats.radius),
                    TokenTypeFilter(token_type=TokenType.SMOKE_BOMB),
                ],
            ),
            SwapUnitsStep(
                unit_a_id=str(hero.id),
                unit_b_key="swap_token_id",
                active_if_key="swap_token_id",
                is_mandatory=False,
            ),
        ]


@register_effect("cobra_stance")
class CobraStanceEffect(CardEffect):
    """
    Target a unit adjacent to you.
    After the attack: You may swap with a Smoke bomb in radius;
    if you do, you may place the Smoke bomb into a space in radius.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # After attack: optional swap with smoke bomb in radius
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select a Smoke Bomb to swap with (optional)",
                output_key="swap_token_id",
                is_mandatory=False,
                skip_immunity_filter=True,
                filters=[
                    RangeFilter(max_range=stats.radius),
                    TokenTypeFilter(token_type=TokenType.SMOKE_BOMB),
                ],
            ),
            SwapUnitsStep(
                unit_a_id=str(hero.id),
                unit_b_key="swap_token_id",
                active_if_key="swap_token_id",
                is_mandatory=False,
            ),
            # If swapped: optionally place the smoke bomb to a new hex in radius
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Place the Smoke Bomb into a space in radius (optional)",
                output_key="smoke_place_hex",
                is_mandatory=False,
                active_if_key="swap_token_id",
                filters=[
                    RangeFilter(max_range=stats.radius),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceTokenStep(
                token_type=TokenType.SMOKE_BOMB,
                hex_key="smoke_place_hex",
                active_if_key="smoke_place_hex",
                is_mandatory=False,
            ),
        ]


# =============================================================================
# GOLD CARD — Fast as Lightning
# =============================================================================


def _find_red_card(hero: Hero) -> "Card | None":
    """Find the hero's resolved or discarded red card for this round."""
    # Check resolved (played_cards)
    for c in hero.played_cards:
        if c is not None and c.color == CardColor.RED:
            return c
    # Check discard pile
    for c in hero.discard_pile:
        if c.color == CardColor.RED:
            return c
    return None


@register_effect("fast_as_lightning")
class FastAsLightningEffect(CardEffect):
    """
    Target a unit in range. After the attack: Apply the "After the attack"
    text of your resolved or discarded red card.
    (If it has radius, use that card's value.)
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        steps: List[GameStep] = [
            AttackSequenceStep(damage=stats.primary_value, range_val=stats.range),
        ]

        red_card = _find_red_card(hero)
        if red_card is None:
            return steps

        effect = CardEffectRegistry.get(red_card.current_effect_id)
        if effect is None:
            return steps

        # Build the red card's steps using the red card's own stats
        from goa2.engine.stats import compute_card_stats

        red_stats = compute_card_stats(state, hero.id, red_card)
        red_steps = effect.build_steps(state, hero, red_card, red_stats)

        # Strip everything up to and including AttackSequenceStep
        after_attack_steps: List[GameStep] = []
        found_attack = False
        for step in red_steps:
            if found_attack:
                after_attack_steps.append(step)
            elif isinstance(step, AttackSequenceStep):
                found_attack = True

        steps.extend(after_attack_steps)
        return steps


# =============================================================================
# GREEN CARDS — Defense: Smoke Bomb Swap
# =============================================================================


def _smoke_bomb_swap_defense_steps(
    defender: Hero, stats: "CardStats", allow_replacement: bool = False
) -> List[GameStep]:
    steps: List[GameStep] = [
        SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Select a Smoke Bomb token to swap with",
            output_key="swap_token_id",
            is_mandatory=False,
            skip_immunity_filter=True,
            filters=[
                RangeFilter(max_range=stats.range),
                TokenTypeFilter(token_type=TokenType.SMOKE_BOMB),
            ],
        ),
        SwapUnitsStep(
            unit_a_id=str(defender.id),
            unit_b_key="swap_token_id",
            active_if_key="swap_token_id",
            is_mandatory=False,
        ),
        SetContextFlagStep(key="auto_block", value=True, active_if_key="swap_token_id"),
    ]
    if allow_replacement:
        steps.append(
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Place the Smoke Bomb into a space in range (optional)",
                output_key="smoke_place_hex",
                is_mandatory=False,
                active_if_key="swap_token_id",
                filters=[
                    RangeFilter(max_range=stats.range),
                    ObstacleFilter(is_obstacle=False),
                ],
            )
        )
        steps.append(
            PlaceTokenStep(
                token_type=TokenType.SMOKE_BOMB,
                hex_key="smoke_place_hex",
                active_if_key="smoke_place_hex",
                is_mandatory=False,
            )
        )
    return steps


@register_effect("poof")
class PoofEffect(CardEffect):
    """
    Swap with a Smoke bomb token in range; if you do, block the attack.
    """

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: "CardStats",
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        return _smoke_bomb_swap_defense_steps(defender, stats)


@register_effect("vanish")
class VanishEffect(CardEffect):
    """
    Swap with a Smoke bomb token in range; if you do, block the attack.
    """

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: "CardStats",
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        return _smoke_bomb_swap_defense_steps(defender, stats)


@register_effect("ruse")
class RuseEffect(CardEffect):
    """
    Swap with a Smoke bomb in range; if you do, block the attack.
    You may place the Smoke bomb into a space in range.
    """

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: "CardStats",
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        return _smoke_bomb_swap_defense_steps(defender, stats, allow_replacement=True)


# =============================================================================
# BLUE CARDS — Grenades
# =============================================================================


def _grenade_steps(hero: Hero, stats: "CardStats", max_targets: int) -> List[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Place Grenade token",
            output_key="grenade_hex",
            is_mandatory=True,
            filters=[
                RangeFilter(max_range=stats.radius),
                ObstacleFilter(is_obstacle=False),
            ],
        ),
        PlaceTokenStep(
            token_type=TokenType.GRENADE,
            hex_key="grenade_hex",
        ),
        CreateEffectStep(
            effect_type=EffectType.DELAYED_TRIGGER,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            is_active=True,
            finishing_steps=[
                SelectStep(
                    target_type=TargetType.UNIT_OR_TOKEN,
                    prompt="Select the Grenade token",
                    output_key="grenade_resolve_id",
                    auto_select_if_one=True,
                    skip_immunity_filter=True,
                    skip_self_filter=True,
                    is_mandatory=False,
                    filters=[TokenTypeFilter(token_type=TokenType.GRENADE)],
                ),
                MultiSelectStep(
                    target_type=TargetType.UNIT,
                    prompt=f"Select up to {max_targets} enemy hero(es) adjacent to grenade",
                    output_key="grenade_victims",
                    max_selections=max_targets,
                    min_selections=0,
                    is_mandatory=False,
                    active_if_key="grenade_resolve_id",
                    skip_immunity_filter=True,
                    filters=[
                        AdjacencyToContextFilter(target_key="grenade_resolve_id"),
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="HERO"),
                    ],
                ),
                ForEachStep(
                    list_key="grenade_victims",
                    item_key="current_victim",
                    steps_template=[
                        ForceDiscardOrDefeatStep(victim_key="current_victim"),
                    ],
                ),
                RemoveTokenStep(token_key="grenade_resolve_id"),
            ],
        ),
    ]


@register_effect("death_grenade")
class DeathGrenadeEffect(CardEffect):
    """
    Place a Grenade token into a space in radius.
    End of turn: Up to 1 enemy hero adjacent to that token discards
    a card, or is defeated. Remove the Grenade token.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: "CardStats"
    ) -> List[GameStep]:
        return _grenade_steps(hero, stats, max_targets=1)


@register_effect("holy_death_grenade")
class HolyDeathGrenadeEffect(CardEffect):
    """
    Place a Grenade token into a space in radius.
    End of turn: Up to 2 enemy heroes adjacent to that token discard
    a card, or are defeated. Remove the Grenade token.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: "CardStats"
    ) -> List[GameStep]:
        return _grenade_steps(hero, stats, max_targets=2)
