from __future__ import annotations
from typing import List, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CheckDistanceStep,
    CheckUnitTypeStep,
    CreateEffectStep,
    DefeatUnitStep,
    ForceDiscardStep,
    GameStep,
    MoveUnitStep,
    PlaceUnitStep,
    PushUnitStep,
    RecordHexStep,
    RetrieveCardStep,
    SelectStep,
    SwapUnitsStep,
)
from goa2.engine.filters import (
    AdjacencyToContextFilter,
    BetweenHexesFilter,
    CountMatchFilter,
    ExcludeIdentityFilter,
    InStraightLineFilter,
    ObstacleFilter,
    RangeFilter,
    RelativeDistanceFilter,
    StraightLinePathFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models import (
    EffectType,
    DurationType,
    StatType,
    TargetType,
)
from goa2.domain.models.effect import EffectScope, AffectsFilter, Shape
from goa2.domain.models.enums import CardContainerType

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


def _has_ultimate(hero: Hero) -> bool:
    return hero.ultimate_card is not None and hero.level >= 8


def _ultimate_post_placement_steps(prefix: str = "ult", active_if_key: str = None) -> List[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Power Overwhelming: Choose an adjacent enemy hero to discard a card",
            filters=[
                RangeFilter(max_range=1),
                TeamFilter(relation="ENEMY"),
                UnitTypeFilter(unit_type="HERO"),
            ],
            is_mandatory=False,
            active_if_key=active_if_key,
            output_key=f"{prefix}_adj_victim",
        ),
        ForceDiscardStep(victim_key=f"{prefix}_adj_victim", active_if_key=f"{prefix}_adj_victim"),
    ]


# =============================================================================
# RED MELEE — Attack Adjacent + Defense Buff (3 tiers)
# =============================================================================


class _RedMeleeEffect(CardEffect):
    """
    Base for RED melee cards: attack adjacent + defense buff.
    Card Text: "Target a unit adjacent to you. After the attack:
    This turn: Gain +N Defense."
    """

    defense_value: int = 2

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        steps: List[GameStep] = [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
            ),
            CreateEffectStep(
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(
                    shape=Shape.POINT,
                    origin_id=hero.id,
                    affects=AffectsFilter.SELF,
                ),
                stat_type=StatType.DEFENSE,
                stat_value=self.defense_value,
                duration=DurationType.THIS_TURN,
                is_active=True,
            ),
        ]
        return steps


@register_effect("challenge_accepted")
class ChallengeAcceptedEffect(_RedMeleeEffect):
    """
    Card Text: "Target a unit adjacent to you. After the attack:
    This turn: Gain +2 Defense."
    """

    defense_value = 2


@register_effect("matter_of_honor")
class MatterOfHonorEffect(_RedMeleeEffect):
    """
    Card Text: "Target a unit adjacent to you. After the attack:
    This turn: Gain +3 Defense."
    """

    defense_value = 3


@register_effect("worthy_opponent")
class WorthyOpponentEffect(_RedMeleeEffect):
    """
    Card Text: "Target a unit adjacent to you. After the attack:
    This turn: Gain +5 Defense."
    """

    defense_value = 5


# =============================================================================
# RED RANGED — Attack + Conditional Push (2 tiers)
# =============================================================================


@register_effect("power_shot")
class PowerShotEffect(CardEffect):
    """
    Card Text: "Target a unit in range. After the attack: If the target was
    at maximum range, you may move it 1 space, to a space farther away from you."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
            ),
            CheckDistanceStep(
                unit_a_id=hero.id,
                unit_b_key="defender_id",
                operator="==",
                threshold=stats.range,
                output_key="ps_can_push",
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move the target to (1 space farther away)",
                output_key="ps_push_dest",
                filters=[
                    RelativeDistanceFilter(reference_key="defender_id", operator=">"),
                    AdjacencyToContextFilter(target_key="defender_id"),
                    ObstacleFilter(is_obstacle=False),
                ],
                active_if_key="ps_can_push",
                is_mandatory=False,
            ),
            MoveUnitStep(
                unit_key="defender_id",
                destination_key="ps_push_dest",
                active_if_key="ps_push_dest",
            ),
        ]


@register_effect("thunder_shot")
class ThunderShotEffect(CardEffect):
    """
    Card Text: "Target a unit in range. After the attack: If the target is
    not adjacent to you, you may move it 1 space, to a space farther away from you."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
            ),
            CheckDistanceStep(
                unit_a_id=hero.id,
                unit_b_key="defender_id",
                operator=">",
                threshold=1,
                output_key="ts_can_push",
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move the target to (1 space farther away)",
                output_key="ts_push_dest",
                filters=[
                    RelativeDistanceFilter(reference_key="defender_id", operator=">"),
                    ObstacleFilter(is_obstacle=False),
                ],
                active_if_key="ts_can_push",
                is_mandatory=False,
            ),
            MoveUnitStep(
                unit_key="defender_id",
                destination_key="ts_push_dest",
                active_if_key="ts_push_dest",
            ),
        ]


# =============================================================================
# BLUE — Straight-Line Move Through (6 cards, shared movement helper)
# =============================================================================


def _blue_move_steps(hero: Hero, max_range: int) -> List[GameStep]:
    return [
        RecordHexStep(unit_id=hero.id, output_key="move_origin"),
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Select destination (straight line, pass through units)",
            output_key="move_dest",
            filters=[
                RangeFilter(min_range=1, max_range=max_range),
                InStraightLineFilter(origin_id=hero.id),
                StraightLinePathFilter(origin_id=hero.id, pass_through_obstacles=True),
                ObstacleFilter(is_obstacle=False),
            ],
            is_mandatory=True,
        ),
        MoveUnitStep(
            unit_id=hero.id,
            destination_key="move_dest",
            range_val=99,
            pass_through_obstacles=True,
        ),
    ]


# -- BLUE Discard variant: dash_and_slash, death_from_above --


class _BlueDiscardEffect(CardEffect):
    """
    Base for BLUE discard cards: straight-line move through, enemy hero discards.
    Card Text: "Move up to N spaces in a straight line, ignoring obstacles;
    an enemy hero you moved through discards a card, if able."
    """

    max_range: int = 3

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        steps = _blue_move_steps(hero, self.max_range)
        steps.extend(
            [

                SelectStep(
                    target_type=TargetType.UNIT,
                    prompt="Select an enemy you moved through",
                    output_key="crossed_enemy",
                    filters=[
                        BetweenHexesFilter(from_hex_key="move_origin", to_hex_key="move_dest"),
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="HERO"),
                    ],
                    is_mandatory=True,
                ),
                ForceDiscardStep(victim_key="crossed_enemy"),
            ]
        )
        return steps


@register_effect("dash_and_slash")
class DashAndSlashEffect(_BlueDiscardEffect):
    """
    Card Text: "Move up to 4 spaces in a straight line, ignoring obstacles;
    an enemy hero you moved through discards a card, if able."
    """

    max_range = 4


@register_effect("death_from_above")
class DeathFromAboveEffect(_BlueDiscardEffect):
    """
    Card Text: "Move up to 5 spaces in a straight line, ignoring obstacles;
    an enemy hero you moved through discards a card, if able."
    """

    max_range = 5


# -- BLUE Place variant: sudden_breeze, gust_of_wind, crushing_squall --


class _BluePlaceEffect(CardEffect):
    """
    Base for BLUE place cards: straight-line move through, place crossed enemy.
    Card Text: "Move up to N spaces in a straight line, ignoring obstacles;
    you may place an enemy unit you moved through into a space adjacent to you."
    """

    max_range: int = 3

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        steps = _blue_move_steps(hero, self.max_range)
        steps.extend(
            [
                
                SelectStep(
                    target_type=TargetType.UNIT,
                    prompt="Select an enemy you moved through",
                    output_key="crossed_enemy",
                    filters=[
                        BetweenHexesFilter(from_hex_key="move_origin", to_hex_key="move_dest"),
                        TeamFilter(relation="ENEMY"),
                    ],
                    is_mandatory=False,
                ),
                SelectStep(
                    target_type=TargetType.HEX,
                    prompt="Place the crossed enemy adjacent to you",
                    output_key="place_dest",
                    filters=[
                        RangeFilter(max_range=1),
                        ObstacleFilter(is_obstacle=False),
                    ],
                    is_mandatory=False,
                    active_if_key="crossed_enemy",
                ),
                PlaceUnitStep(
                    unit_key="crossed_enemy",
                    destination_key="place_dest",
                    active_if_key="place_dest",
                ),
            ]
        )
        return steps


@register_effect("sudden_breeze")
class SuddenBreezeEffect(_BluePlaceEffect):
    """
    Card Text: "Move up to 3 spaces in a straight line, ignoring obstacles;
    you may place an enemy unit you moved through into a space adjacent to you."
    """

    max_range = 3


@register_effect("gust_of_wind")
class GustOfWindEffect(_BluePlaceEffect):
    """
    Card Text: "Move up to 4 spaces in a straight line, ignoring obstacles;
    you may place an enemy unit you moved through into a space adjacent to you."
    """

    max_range = 4


@register_effect("crushing_squall")
class CrushingSquallEffect(_BluePlaceEffect):
    """
    Card Text: "Move up to 5 spaces in a straight line, ignoring obstacles;
    you may place an enemy unit you moved through into a space adjacent to you."
    """

    max_range = 5


# =============================================================================
# GREEN — Swap Two Units (2 tiers)
# =============================================================================


@register_effect("living_tornado")
class LivingTornadoEffect(CardEffect):
    """
    Card Text: "Swap two units at maximum radius."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        r = stats.radius
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select first unit to swap (at max radius)",
                output_key="swap_a",
                filters=[RangeFilter(min_range=r, max_range=r)],
                is_mandatory=True,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select second unit to swap (at max radius)",
                output_key="swap_b",
                filters=[
                    RangeFilter(min_range=r, max_range=r),
                    ExcludeIdentityFilter(exclude_keys=["swap_a"]),
                ],
                is_mandatory=True,
            ),
            SwapUnitsStep(unit_a_key="swap_a", unit_b_key="swap_b"),
        ]


@register_effect("storm_spirit")
class StormSpiritEffect(CardEffect):
    """
    Card Text: "Swap two units in radius and at equal distance from you."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        r = stats.radius
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select first unit to swap (in radius)",
                output_key="swap_a",
                filters=[RangeFilter(max_range=r)],
                is_mandatory=True,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select second unit (in radius, same distance)",
                output_key="swap_b",
                filters=[
                    RangeFilter(max_range=r),
                    ExcludeIdentityFilter(exclude_keys=["swap_a"]),
                    RelativeDistanceFilter(reference_key="swap_a", operator="=="),
                ],
                is_mandatory=True,
            ),
            SwapUnitsStep(unit_a_key="swap_a", unit_b_key="swap_b"),
        ]


# =============================================================================
# GREEN — Next-Turn Pre-Action Movement (3 tiers)
# =============================================================================


class _GreenPreActionMoveEffect(CardEffect):
    """
    Base for GREEN pre-action movement cards.
    Card Text: "Next turn: Before you perform a primary action, move up to N spaces."
    """

    move_distance: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.PRE_ACTION_MOVEMENT,
                scope=EffectScope(
                    shape=Shape.POINT,
                    origin_id=hero.id,
                    affects=AffectsFilter.SELF,
                ),
                duration=DurationType.NEXT_TURN,
                max_value=self.move_distance,
                is_active=True,
            ),
        ]


@register_effect("focus")
class FocusEffect(_GreenPreActionMoveEffect):
    """
    Card Text: "Next turn: Before you perform a primary action, you may move 1 space."
    """

    move_distance = 1


@register_effect("discipline")
class DisciplineEffect(_GreenPreActionMoveEffect):
    """
    Card Text: "Next turn: Before you perform a primary action, move up to 2 spaces."
    """

    move_distance = 2


@register_effect("mastery")
class MasteryEffect(_GreenPreActionMoveEffect):
    """
    Card Text: "Next turn: Before you perform a primary action, move up to 3 spaces."
    """

    move_distance = 3


# =============================================================================
# SILVER — Swoop In
# =============================================================================


@register_effect("swoop_in")
class SwoopInEffect(CardEffect):
    """
    Card Text: "Place yourself into a space in radius adjacent to two or more
    enemy units; if you do, you may retrieve a discarded card."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        steps: List[GameStep] = [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Place yourself adjacent to 2+ enemy units",
                output_key="swoop_dest",
                filters=[
                    RangeFilter(max_range=stats.radius),
                    ObstacleFilter(is_obstacle=False),
                    CountMatchFilter(
                        sub_filters=[
                            RangeFilter(
                                max_range=1,
                                origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY,
                            ),
                            TeamFilter(relation="ENEMY"),
                        ],
                        min_count=2,
                    ),
                ],
                is_mandatory=True,
            ),
            PlaceUnitStep(unit_id=hero.id, destination_key="swoop_dest"),
            SelectStep(
                target_type=TargetType.CARD,
                prompt="Retrieve a discarded card?",
                output_key="swoop_retrieved",
                card_container=CardContainerType.DISCARD,
                is_mandatory=False,
            ),
            RetrieveCardStep(
                card_key="swoop_retrieved",
                active_if_key="swoop_retrieved",
            ),
        ]
        if _has_ultimate(hero):
            steps.extend(_ultimate_post_placement_steps("swoop_ult"))
        return steps


# =============================================================================
# GOLD — Watch How I Soar (Choose One / Choose Two with Ultimate)
# =============================================================================


@register_effect("watch_how_i_soar")
class WatchHowISoarEffect(CardEffect):
    """
    Card Text: "Choose one —
    • Place yourself into a space at maximum range.
    • Defeat a minion adjacent to you."

    With Power Overwhelming ultimate: choose two different options instead.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        has_ult = _has_ultimate(hero)

        steps: List[GameStep] = [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="soar_choice",
                number_options=[1, 2],
                number_labels={
                    1: "Place yourself at maximum range",
                    2: "Defeat an adjacent minion",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="soar_choice",
                operator="==",
                threshold=1,
                output_key="chose_place",
            ),
            CheckContextConditionStep(
                input_key="soar_choice",
                operator="==",
                threshold=2,
                output_key="chose_defeat",
            ),
            # Path A: place at max range
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select destination at maximum range",
                output_key="soar_dest",
                filters=[
                    RangeFilter(min_range=stats.range, max_range=stats.range),
                    ObstacleFilter(is_obstacle=False),
                ],
                active_if_key="chose_place",
                is_mandatory=True,
            ),
            PlaceUnitStep(
                unit_id=hero.id,
                destination_key="soar_dest",
                active_if_key="chose_place",
            ),
            # Path B: defeat adjacent minion
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an adjacent enemy minion to defeat",
                output_key="soar_defeat_target",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="MINION"),
                ],
                active_if_key="chose_defeat",
                is_mandatory=True,
            ),
            DefeatUnitStep(
                victim_key="soar_defeat_target",
                active_if_key="chose_defeat",
            ),
        ]

        if has_ult:
            # If chose place (1), also offer defeat
            steps.extend(
                [
                    *_ultimate_post_placement_steps(prefix="soar_ult_a", active_if_key="chose_place"),
                    SelectStep(
                        target_type=TargetType.UNIT,
                        prompt="Power Overwhelming: Also defeat an adjacent minion?",
                        output_key="soar_ult_defeat_target",
                        filters=[
                            RangeFilter(max_range=1),
                            TeamFilter(relation="ENEMY"),
                            UnitTypeFilter(unit_type="MINION"),
                        ],
                        is_mandatory=False,
                        active_if_key="chose_place",
                    ),
                    DefeatUnitStep(
                        victim_key="soar_ult_defeat_target",
                        active_if_key="soar_ult_defeat_target",
                    ),
                ]
            )
            # If chose defeat (2), also offer place
            steps.extend(
                [
                    SelectStep(
                        target_type=TargetType.HEX,
                        prompt="Power Overwhelming: Also place at max range?",
                        output_key="soar_ult_dest",
                        filters=[
                            RangeFilter(min_range=stats.range, max_range=stats.range),
                            ObstacleFilter(is_obstacle=False),
                        ],
                        is_mandatory=False,
                        active_if_key="chose_defeat",
                    ),
                    PlaceUnitStep(
                        unit_id=hero.id,
                        destination_key="soar_ult_dest",
                        active_if_key="soar_ult_dest",
                    ),
                    *_ultimate_post_placement_steps(prefix="soar_ult_b", active_if_key="soar_ult_dest")
                ]
            )

        return steps
