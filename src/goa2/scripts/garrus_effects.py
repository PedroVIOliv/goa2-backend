from __future__ import annotations
from typing import List, TYPE_CHECKING, Optional
from goa2.engine.effects import CardEffect, PassiveConfig, register_effect, CardEffectRegistry
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CountCardsStep,
    CountStep,
    CreateEffectStep,
    DiscardCardStep,
    ForceDiscardStep,
    ForceDiscardOrDefeatStep,
    GameStep,
    MayRepeatNTimesStep,
    MoveSequenceStep,
    MoveUnitStep,
    PushUnitStep,
    RetrieveCardStep,
    SelectStep,
)
from goa2.engine.filters import (
    AdjacencyFilter,
    AdjacencyToContextFilter,
    MovementPathFilter,
    ObstacleFilter,
    RangeFilter,
    RelativeDistanceFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models import (
    ActionType,
    CardColor,
    DurationType,
    EffectType,
    StatType,
    TargetType,
)
from goa2.domain.models.effect import AffectsFilter, EffectScope, Shape
from goa2.domain.models.enums import CardContainerType, PassiveTrigger

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


# =============================================================================
# RED — Charge Attack (Trace / Chase / Hunt Down)
# =============================================================================


class _ChargeAttackEffect(CardEffect):
    """
    Card Text: "Choose one —
    • Before the attack: If you have one or more cards in the discard,
      move up to N spaces. Target a hero adjacent to you.
    • Target a unit adjacent to you."
    """

    move_distance: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="charge_choice",
                number_options=[1, 2],
                number_labels={
                    1: f"Charge: move up to {self.move_distance}, attack adjacent hero",
                    2: "Attack a unit adjacent to you",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="charge_choice",
                operator="==",
                threshold=1,
                output_key="chose_charge",
            ),
            CheckContextConditionStep(
                input_key="charge_choice",
                operator="==",
                threshold=2,
                output_key="chose_standard",
            ),
            # Charge branch: discard pile must be non-empty, then move, then attack hero
            CountCardsStep(
                hero_id=hero.id,
                card_container=CardContainerType.DISCARD,
                output_key="charge_discard_count",
                active_if_key="chose_charge",
            ),
            CheckContextConditionStep(
                input_key="charge_discard_count",
                operator=">=",
                threshold=1,
                output_key="charge_has_discard",
                active_if_key="chose_charge",
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"Move up to {self.move_distance} spaces",
                output_key="charge_move_dest",
                filters=[
                    RangeFilter(max_range=self.move_distance),
                    MovementPathFilter(
                        range_val=self.move_distance,
                    ), 
                    ObstacleFilter(is_obstacle=False),
                ],
                is_mandatory=False,
                active_if_key="charge_has_discard",
            ),
            MoveUnitStep(
                unit_id=hero.id,
                destination_key="charge_move_dest",
                range_val=self.move_distance,
                active_if_key="charge_move_dest",
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                target_filters=[UnitTypeFilter(unit_type="HERO")],
                active_if_key="chose_charge",
            ),
            # Standard branch: attack any adjacent unit
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                active_if_key="chose_standard",
            ),
        ]


@register_effect("trace")
class TraceEffect(_ChargeAttackEffect):
    move_distance = 1


@register_effect("chase")
class ChaseEffect(_ChargeAttackEffect):
    move_distance = 2


@register_effect("hunt_down")
class HuntDownEffect(_ChargeAttackEffect):
    move_distance = 3


# =============================================================================
# RED — Dash + Push (Blunt Force / Send Flying)
# =============================================================================


class _DashPushEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you. After the attack: You may move
    up to N spaces to a space adjacent to an enemy hero; if you do, push that
    hero 3 spaces, ignoring obstacles."
    """

    dash_distance: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"Move up to {self.dash_distance} to a space adjacent to an enemy hero",
                output_key="dash_dest",
                filters=[
                    RangeFilter(max_range=self.dash_distance),
                    MovementPathFilter(range_val=self.dash_distance),
                    AdjacencyFilter(target_tags=["ENEMY","HERO"], skip_immune=True),
                    ObstacleFilter(is_obstacle=False),
                ],
                is_mandatory=False,
            ),
            MoveUnitStep(
                unit_id=hero.id,
                destination_key="dash_dest",
                range_val=self.dash_distance,
                active_if_key="dash_dest",
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an adjacent enemy hero to push 3 spaces",
                output_key="dash_push_target",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                ],
                is_mandatory=True,
                active_if_key="dash_dest",
            ),
            PushUnitStep(
                target_key="dash_push_target",
                distance=3,
                ignore_obstacles=True,
                active_if_key="dash_push_target",
            ),
        ]


@register_effect("blunt_force")
class BluntForceEffect(_DashPushEffect):
    dash_distance = 1


@register_effect("send_flying")
class SendFlyingEffect(_DashPushEffect):
    dash_distance = 2


# =============================================================================
# BLUE — Pull Friendly Closer (Form Up! / Testudo!)
# =============================================================================


class _PullFriendlyEffect(CardEffect):
    """
    Card Text: "Move a friendly unit in range 1 space to a space closer to you.
    May repeat [once / up to two times]."
    """

    repeats: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        pull_template: List[GameStep] = [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select a friendly unit in range to pull closer",
                output_key="pull_target",
                filters=[
                    RangeFilter(max_range=stats.range),
                    TeamFilter(relation="FRIENDLY"),
                ],
                is_mandatory=True,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space 1 closer to you",
                output_key="pull_dest",
                filters=[
                    AdjacencyToContextFilter(target_key="pull_target"),
                    RelativeDistanceFilter(reference_key="pull_target", operator="<"),
                    ObstacleFilter(is_obstacle=False),
                ],
                is_mandatory=True,
            ),
            MoveUnitStep(
                unit_key="pull_target",
                destination_key="pull_dest",
                range_val=1,
            ),
        ]
        return [
            *pull_template,
            MayRepeatNTimesStep(
                max_repeats=self.repeats,
                steps_template=pull_template,
                prompt="Pull another friendly unit?",
            ),
        ]


@register_effect("form_up")
class FormUpEffect(_PullFriendlyEffect):
    repeats = 1


@register_effect("testudo")
class TestudoEffect(_PullFriendlyEffect):
    repeats = 2


# =============================================================================
# BLUE — Push Enemy Farther (Menace / Threaten / Terrify)
# =============================================================================


class _PushEnemyEffect(CardEffect):
    """
    Card Text: "Move an enemy unit in range 1 space to a space farther away
    from you. [May repeat once / May repeat up to two times.]"
    """

    repeats: int = 0

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        push_template: List[GameStep] = [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy unit in range to push farther",
                output_key="push_target",
                filters=[
                    RangeFilter(max_range=stats.range),
                    TeamFilter(relation="ENEMY"),
                ],
                is_mandatory=True,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space 1 farther from you",
                output_key="push_dest",
                filters=[
                    AdjacencyToContextFilter(target_key="push_target"),
                    RelativeDistanceFilter(reference_key="push_target", operator=">"),
                    ObstacleFilter(is_obstacle=False),
                ],
                is_mandatory=True,
            ),
            MoveUnitStep(
                unit_key="push_target",
                destination_key="push_dest",
                range_val=1,
            ),
        ]
        steps: List[GameStep] = [*push_template]
        if self.repeats > 0:
            steps.append(
                MayRepeatNTimesStep(
                    max_repeats=self.repeats,
                    steps_template=push_template,
                    prompt="Push another enemy?",
                )
            )
        return steps


@register_effect("menace")
class MenaceEffect(_PushEnemyEffect):
    repeats = 0


@register_effect("threaten")
class ThreatenEffect(_PushEnemyEffect):
    repeats = 1


@register_effect("terrify")
class TerrifyEffect(_PushEnemyEffect):
    repeats = 2


# =============================================================================
# GREEN — Conditional Retrieval (Hold Ground / Make a Stand / Battle Ready)
# =============================================================================


class _ConditionalRetrieveEffect(CardEffect):
    """
    Card Text: "If there are at least two enemy heroes in radius, you may
    retrieve [a discarded card / up to two discarded cards]."
    """

    max_retrieves: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        steps: List[GameStep] = [
            CountStep(
                target_type=TargetType.UNIT,
                filters=[
                    RangeFilter(max_range=stats.radius or 0),
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                ],
                output_key="enemy_hero_count",
            ),
            CheckContextConditionStep(
                input_key="enemy_hero_count",
                operator=">=",
                threshold=2,
                output_key="can_retrieve",
            ),
        ]
        for i in range(self.max_retrieves):
            steps.extend(
                [
                    SelectStep(
                        target_type=TargetType.CARD,
                        card_container=CardContainerType.DISCARD,
                        prompt=f"Select a discarded card to retrieve ({i + 1})",
                        output_key=f"retrieve_card_{i}",
                        is_mandatory=False,
                        active_if_key="can_retrieve",
                    ),
                    RetrieveCardStep(
                        card_key=f"retrieve_card_{i}",
                        active_if_key=f"retrieve_card_{i}",
                    ),
                ]
            )
        return steps


@register_effect("hold_ground")
class HoldGroundEffect(_ConditionalRetrieveEffect):
    max_retrieves = 1


@register_effect("make_a_stand")
class MakeAStandEffect(_ConditionalRetrieveEffect):
    max_retrieves = 1


@register_effect("battle_ready")
class BattleReadyEffect(_ConditionalRetrieveEffect):
    max_retrieves = 2


# =============================================================================
# GREEN — Forced Discard (Light Pilum / Heavy Pilum)
# =============================================================================


@register_effect("light_pilum")
class LightPilumEffect(CardEffect):
    """
    Card Text: "An enemy hero in range discards a card, if able.
    You may move 1 space."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero in range",
                output_key="pilum_victim",
                filters=[
                    RangeFilter(max_range=stats.range),
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                ],
                is_mandatory=True,
            ),
            ForceDiscardStep(victim_key="pilum_victim"),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Move 1 space",
                output_key="pilum_move_dest",
                filters=[
                    RangeFilter(max_range=1),
                    MovementPathFilter(range_val=1),
                    ObstacleFilter(is_obstacle=False),
                ],
                is_mandatory=False,
            ),
            MoveUnitStep(
                unit_id=hero.id,
                destination_key="pilum_move_dest",
                range_val=1,
                active_if_key="pilum_move_dest",
            ),
        ]


@register_effect("heavy_pilum")
class HeavyPilumEffect(CardEffect):
    """
    Card Text: "An enemy hero in range discards a card, or is defeated.
    You may move up to 2 spaces."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero in range",
                output_key="pilum_victim",
                filters=[
                    RangeFilter(max_range=stats.range),
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                ],
                is_mandatory=True,
            ),
            ForceDiscardOrDefeatStep(victim_key="pilum_victim"),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Move up to 2 spaces",
                output_key="pilum_move_dest",
                filters=[
                    RangeFilter(max_range=2),
                    MovementPathFilter(range_val=2),
                    ObstacleFilter(is_obstacle=False),
                ],
                is_mandatory=False,
            ),
            MoveUnitStep(
                unit_id=hero.id,
                destination_key="pilum_move_dest",
                range_val=2,
                active_if_key="pilum_move_dest",
            ),
        ]


# =============================================================================
# GOLD — Angry Strike
# =============================================================================


@register_effect("angry_strike")
class AngryStrikeEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you; +1 Attack for every card in
    your discard."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CountCardsStep(
                hero_id=hero.id,
                card_container=CardContainerType.DISCARD,
                output_key="angry_discard_count",
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                damage_bonus_key="angry_discard_count",
            ),
        ]


# =============================================================================
# SILVER — Chilling Howl
# =============================================================================


@register_effect("chilling_howl")
class ChillingHowlEffect(CardEffect):
    """
    Card Text: "You may discard one of your resolved cards. This round:
    Enemy heroes in radius cannot fast travel, or move more than 2 spaces
    with a movement action."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.PLAYED,
                prompt="Optionally discard one of your resolved cards",
                output_key="howl_discard_card",
                is_mandatory=False,
            ),
            DiscardCardStep(
                card_key="howl_discard_card",
                hero_id=hero.id,
                source=CardContainerType.PLAYED,
                active_if_key="howl_discard_card",
            ),
            CreateEffectStep(
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_ROUND,
                max_value=2,
                limit_actions_only=True,
                restrictions=[ActionType.FAST_TRAVEL],
            ),
        ]


# =============================================================================
# PURPLE — Battle Fury (Ultimate Passive)
# =============================================================================


@register_effect("battle_fury")
class BattleFuryEffect(CardEffect):
    """
    Card Text: "Each time after one of your resolved cards is discarded, you
    may perform its primary action."
    """

    def get_passive_config(self) -> Optional[PassiveConfig]:
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_CARD_DISCARD,
            uses_per_turn=0,  # unlimited — chains allowed
            is_optional=True,
            prompt="Battle Fury: Perform the discarded card's primary action?",
        )

    def should_offer_passive(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict,
    ) -> bool:
        # Only fire when a resolved (played) card is discarded and the
        # discarded card belongs to Garrus.
        if context.get("discard_source") != CardContainerType.PLAYED.value:
            return False
        if context.get("discarded_card_owner_id") != str(hero.id):
            return False
        return True

    def get_passive_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict,
    ) -> List[GameStep]:
        if trigger != PassiveTrigger.AFTER_CARD_DISCARD:
            return []

        discarded_id = context.get("discarded_card_id")
        if not discarded_id:
            return []

        # Find discarded card in hero's discard pile
        discarded = next(
            (c for c in hero.discard_pile if c.id == discarded_id), None
        )
        if not discarded:
            return []

        primary = discarded.primary_action
        if not primary:
            return []


        effect = CardEffectRegistry.get(discarded.effect_id)
        if effect:
            return effect.get_steps(state, hero, discarded)

        return []
