from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from goa2.engine.effects import CardEffect, PassiveConfig, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    ComputeHexStep,
    CreateEffectStep,
    DiscardCardStep,
    ForceDiscardStep,
    GainCoinsStep,
    GameStep,
    GuessCardColorStep,
    MoveSequenceStep,
    MoveUnitStep,
    PlaceMarkerStep,
    RemoveMarkerStep,
    RetrieveCardStep,
    RevealAndResolveGuessStep,
    SelectStep,
    SetContextFlagStep,
)
from goa2.engine.filters import (
    CardsInContainerFilter,
    ClearLineOfSightFilter,
    ExcludeIdentityFilter,
    HasMarkerFilter,
    InStraightLineFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models.marker import MarkerType
from goa2.domain.models.enums import CardContainerType, PassiveTrigger, TargetType
from goa2.domain.models.effect import DurationType, EffectType, EffectScope, Shape

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


# =============================================================================
# Shared Helpers
# =============================================================================


def _bounty_marker_in_play(state: "GameState") -> bool:
    """Check if any hero in play currently has the Bounty marker."""
    marker = state.markers.get(MarkerType.BOUNTY)
    return marker is not None and marker.is_placed


# =============================================================================
# CROSSBOW CARDS: Light Crossbow / Heavy Crossbow / Arbalest
# =============================================================================


class _CrossbowEffect(CardEffect):
    """
    Base for crossbow cards: "Target a unit in range and in a straight line
    with no units or terrain between you."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                target_filters=[
                    InStraightLineFilter(),
                    ClearLineOfSightFilter(
                        blocked_by_units=True, blocked_by_terrain=True
                    ),
                ],
            ),
        ]


@register_effect("light_crossbow")
class LightCrossbowEffect(_CrossbowEffect):
    """
    Card Text: "Target a unit in range and in a straight line with no units
    or terrain between you."
    """

    pass


@register_effect("heavy_crossbow")
class HeavyCrossbowEffect(_CrossbowEffect):
    """
    Card Text: "Target a unit in range and in a straight line with no units
    or terrain between you."
    """

    pass


@register_effect("arbalest")
class ArbalestEffect(_CrossbowEffect):
    """
    Card Text: "Target a unit in range and in a straight line with no units
    or terrain between you."
    """

    pass


# =============================================================================
# DEFENSE CARDS: Close Call / Narrow Escape / Perfect Getaway
# =============================================================================


@register_effect("perfect_getaway")
class PerfectGetawayEffect(CardEffect):
    """
    Card Text: "If a hero in play has a Bounty marker, block the attack."
    """

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        if _bounty_marker_in_play(state):
            return [SetContextFlagStep(key="auto_block", value=True)]
        return [SetContextFlagStep(key="defense_invalid", value=True)]


@register_effect("close_call")
class CloseCallEffect(CardEffect):
    """
    Card Text: "If a hero in play has a Bounty marker, block the attack and
    that hero gives the marker to you. (The marker's effect is applied to you.)"
    """

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        if _bounty_marker_in_play(state):
            return [
                SetContextFlagStep(key="auto_block", value=True),
                PlaceMarkerStep(
                    marker_type=MarkerType.BOUNTY,
                    target_id=str(defender.id),
                    value=0,
                ),
            ]
        return [SetContextFlagStep(key="defense_invalid", value=True)]


@register_effect("narrow_escape")
class NarrowEscapeEffect(CardEffect):
    """
    Card Text: "If a hero in play has a Bounty marker, block the attack and
    retrieve the marker."
    """

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        if _bounty_marker_in_play(state):
            return [
                SetContextFlagStep(key="auto_block", value=True),
                RemoveMarkerStep(marker_type=MarkerType.BOUNTY),
            ]
        return [SetContextFlagStep(key="defense_invalid", value=True)]


# =============================================================================
# MOVEMENT CARDS: Vantage Point / High Ground
# =============================================================================


class _IgnoreObstaclesMovementEffect(CardEffect):
    """
    Base for movement cards: "Ignore obstacles. If a hero in play has a
    Bounty marker, +N movement."
    """

    bounty_bonus: int = 0

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        movement_value = stats.primary_value
        if _bounty_marker_in_play(state):
            movement_value += self.bounty_bonus
        return [
            MoveSequenceStep(
                range_val=movement_value, pass_through_obstacles=True
            ),
        ]


@register_effect("vantage_point")
class VantagePointEffect(_IgnoreObstaclesMovementEffect):
    """
    Card Text: "Ignore obstacles. If a hero in play has a Bounty marker,
    +1 movement."
    """

    bounty_bonus: int = 1


@register_effect("high_ground")
class HighGroundEffect(_IgnoreObstaclesMovementEffect):
    """
    Card Text: "Ignore obstacles. If a hero in play has a Bounty marker,
    +2 movement."
    """

    bounty_bonus: int = 2


# =============================================================================
# ATTACK CARDS: Dead or Alive / Hand Crossbow / Hunter-Seeker
# =============================================================================


@register_effect("dead_or_alive")
class DeadOrAliveEffect(CardEffect):
    """
    Card Text: "Target a unit adjacent to you.
    After the attack: You may give an enemy hero in play the Bounty marker.
    A hero with the Bounty marker spends 1 additional Life counter when defeated."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="You may give an enemy hero the Bounty marker",
                output_key="bounty_target",
                is_mandatory=False,
                skip_immunity_filter=True,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                ],
            ),
            PlaceMarkerStep(
                marker_type=MarkerType.BOUNTY,
                target_key="bounty_target",
                value=0,
            ),
        ]


@register_effect("hand_crossbow")
class HandCrossbowEffect(CardEffect):
    """
    Card Text: "Choose one —
    * Target a hero in range with a Bounty marker.
    * Target a unit adjacent to you."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Choose mode
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Target hero with Bounty marker in range, 2 = Target adjacent unit",
                output_key="hc_choice",
                number_options=[1, 2],
                is_mandatory=True,
            ),
            # 2. Branch flags
            CheckContextConditionStep(
                input_key="hc_choice",
                operator="==",
                threshold=1,
                output_key="chose_bounty",
            ),
            CheckContextConditionStep(
                input_key="hc_choice",
                operator="==",
                threshold=2,
                output_key="chose_adjacent",
            ),
            # 3a. Bounty target: hero in range with Bounty marker
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                active_if_key="chose_bounty",
                target_filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    HasMarkerFilter(marker_type=MarkerType.BOUNTY),
                ],
            ),
            # 3b. Adjacent: standard melee attack
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=True,
                active_if_key="chose_adjacent",
            ),
        ]


@register_effect("hunter_seeker")
class HunterSeekerEffect(CardEffect):
    """
    Card Text: "Choose one, or both, on different targets —
    * Target a hero in range with a Bounty marker.
    * Target a unit adjacent to you."

    Two-step flow: player picks which attack to do first, then is optionally
    offered the other attack on a different target.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Choose which attack to do first
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Target hero with Bounty first, 2 = Target adjacent unit first",
                output_key="hs_choice",
                number_options=[1, 2],
                is_mandatory=True,
            ),
            # 2. Branch flags
            CheckContextConditionStep(
                input_key="hs_choice",
                operator="==",
                threshold=1,
                output_key="chose_bounty_first",
            ),
            CheckContextConditionStep(
                input_key="hs_choice",
                operator="==",
                threshold=2,
                output_key="chose_adjacent_first",
            ),
            # --- PATH A: Bounty target first ---
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                active_if_key="chose_bounty_first",
                target_filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    HasMarkerFilter(marker_type=MarkerType.BOUNTY),
                ],
            ),
            # Optionally target adjacent unit (different target)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Optionally target an adjacent unit (different target)",
                output_key="hs_second_victim",
                is_mandatory=False,
                active_if_key="chose_bounty_first",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                    ExcludeIdentityFilter(
                        exclude_self=False,
                        exclude_keys=["victim_id"],
                    ),
                ],
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=True,
                target_id_key="hs_second_victim",
                active_if_key="hs_second_victim",
            ),
            # --- PATH B: Adjacent first ---
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=True,
                active_if_key="chose_adjacent_first",
            ),
            # Optionally target hero in range with bounty (different target)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Optionally target a hero with Bounty marker in range (different target)",
                output_key="hs_second_victim",
                is_mandatory=False,
                active_if_key="chose_adjacent_first",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                    HasMarkerFilter(marker_type=MarkerType.BOUNTY),
                    ExcludeIdentityFilter(
                        exclude_self=False,
                        exclude_keys=["victim_id"],
                    ),
                ],
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                target_id_key="hs_second_victim",
                active_if_key="hs_second_victim",
            ),
        ]


# =============================================================================
# CARD RETRIEVAL: Drinking Buddies / Another One!
# =============================================================================


def _build_retrieve_steps(stats: "CardStats") -> List["GameStep"]:
    """Shared retrieve sequence for Drinking Buddies and Another One!.

    1. Optionally select a hero in radius with cards in discard.
    2. That hero selects a card from their discard (target chooses).
    3. That hero retrieves the card.
    4. If step 1 was not skipped, Bain may also select a card from own discard.
    5. Bain retrieves the card.
    """
    return [
        # 1. Select any hero in radius who has discarded cards (optional)
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="You may have a hero in radius retrieve a discarded card",
            output_key="retrieve_target",
            is_mandatory=False,
            skip_immunity_filter=True,
            filters=[
                RangeFilter(max_range=stats.radius),
                UnitTypeFilter(unit_type="HERO"),
                CardsInContainerFilter(container=CardContainerType.DISCARD, min_cards=1),
            ],
        ),
        # 2. Target hero selects card from their discard
        SelectStep(
            target_type=TargetType.CARD,
            card_container=CardContainerType.DISCARD,
            context_hero_id_key="retrieve_target",
            override_player_id_key="retrieve_target",
            prompt="Select a discarded card to retrieve",
            output_key="target_retrieve_card",
            is_mandatory=True,
            active_if_key="retrieve_target",
        ),
        # 3. Target hero retrieves the card
        RetrieveCardStep(
            card_key="target_retrieve_card",
            hero_key="retrieve_target",
            active_if_key="retrieve_target",
        ),
        # 4. Bain may also select a card from own discard
        SelectStep(
            target_type=TargetType.CARD,
            card_container=CardContainerType.DISCARD,
            prompt="You may also retrieve a discarded card",
            output_key="actor_retrieve_card",
            is_mandatory=False,
            active_if_key="retrieve_target",
        ),
        # 5. Bain retrieves the card
        RetrieveCardStep(
            card_key="actor_retrieve_card",
            active_if_key="actor_retrieve_card",
        ),
    ]


@register_effect("drinking_buddies")
class DrinkingBuddiesEffect(CardEffect):
    """
    Card Text: "You may have a hero in radius retrieve a discarded card.
    If they do, you may also retrieve a discarded card."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return _build_retrieve_steps(stats)


@register_effect("another_one")
class AnotherOneEffect(CardEffect):
    """
    Card Text: "You may have a hero in radius retrieve a discarded card.
    If they do, you may also retrieve a discarded card.
    End of turn: May repeat once."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            *_build_retrieve_steps(stats),
            # Delayed trigger: repeat the retrieve sequence at end of turn
            CreateEffectStep(
                effect_type=EffectType.DELAYED_TRIGGER,
                duration=DurationType.THIS_TURN,
                scope=EffectScope(shape=Shape.POINT),
                is_active=True,
                finishing_steps=_build_retrieve_steps(stats),
            ),
        ]


# =============================================================================
# GUESS MECHANIC: A Game of Chance / Dead Man's Hand / We're Not Done Yet!
# =============================================================================


def _build_guess_steps(
    stats: "CardStats", consolation_coins: int, prefix: str = ""
) -> List["GameStep"]:
    """Shared guess-card-color sequence.

    1. Select enemy hero in radius with 2+ cards in hand.
    2. That enemy chooses a card from their hand (opponent input).
    3. Actor guesses the card's color from valid options.
    4. Reveal and compare.
    5. If correct: discard that card from enemy's hand.
    6. If wrong: actor gains consolation_coins gold.

    The prefix parameter namespaces context keys to avoid collisions when
    the sequence is used multiple times (e.g., repeat mechanic).
    """
    p = f"{prefix}_" if prefix else ""
    return [
        # Store actor ID for coin gain
        SetContextFlagStep(key=f"{p}guess_actor", value=None),  # placeholder
        # 1. Select enemy hero with 2+ cards
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select an enemy hero with two or more cards in hand",
            output_key=f"{p}guess_victim",
            is_mandatory=True,
            filters=[
                TeamFilter(relation="ENEMY"),
                UnitTypeFilter(unit_type="HERO"),
                RangeFilter(max_range=stats.radius),
                CardsInContainerFilter(
                    container=CardContainerType.HAND, min_cards=2
                ),
            ],
        ),
        # 2. Enemy chooses a card from their hand
        SelectStep(
            target_type=TargetType.CARD,
            card_container=CardContainerType.HAND,
            context_hero_id_key=f"{p}guess_victim",
            override_player_id_key=f"{p}guess_victim",
            prompt="Choose one of your cards",
            output_key=f"{p}chosen_card",
            is_mandatory=True,
        ),
        # 3. Actor guesses the card's color
        GuessCardColorStep(
            output_key=f"{p}guessed_color",
        ),
        # 4. Reveal and resolve
        RevealAndResolveGuessStep(
            card_key=f"{p}chosen_card",
            guess_key=f"{p}guessed_color",
            victim_key=f"{p}guess_victim",
            correct_output_key=f"{p}guess_correct",
            wrong_output_key=f"{p}guess_wrong",
        ),
        # 5. If correct: discard that card
        DiscardCardStep(
            card_key=f"{p}chosen_card",
            hero_key=f"{p}guess_victim",
            active_if_key=f"{p}guess_correct",
        ),
        # 6. If wrong: gain coins
        GainCoinsStep(
            hero_key=f"{p}guess_actor",
            amount=consolation_coins,
            active_if_key=f"{p}guess_wrong",
        ),
    ]


@register_effect("a_game_of_chance")
class AGameOfChanceEffect(CardEffect):
    """
    Card Text: "An enemy hero in radius with two or more cards in hand
    chooses one of those cards. Guess that card's color, then reveal it.
    If you guessed correctly, discard that card; otherwise you gain 1 coin."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        steps = _build_guess_steps(stats, consolation_coins=1)
        # Patch the actor placeholder with actual hero ID
        steps[0] = SetContextFlagStep(key="guess_actor", value=str(hero.id))
        return steps


@register_effect("dead_mans_hand")
class DeadMansHandEffect(CardEffect):
    """
    Card Text: "An enemy hero in radius with two or more cards in hand
    chooses one of those cards. Guess that card's color, then reveal it.
    If you guessed correctly, discard that card; otherwise you gain 2 coins."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        steps = _build_guess_steps(stats, consolation_coins=2)
        steps[0] = SetContextFlagStep(key="guess_actor", value=str(hero.id))
        return steps


@register_effect("were_not_done_yet")
class WereNotDoneYetEffect(CardEffect):
    """
    Card Text: "An enemy hero in radius with two or more cards in hand
    chooses one of those cards. Guess that card's color, then reveal it.
    If you guessed correctly, discard that card; otherwise may repeat once
    or gain 2 coins."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        # Build the base guess sequence (without the wrong-guess coin gain)
        steps = _build_guess_steps(stats, consolation_coins=0)
        steps[0] = SetContextFlagStep(key="guess_actor", value=str(hero.id))
        # Remove the default GainCoinsStep (last step, amount=0 is useless)
        steps.pop()

        # On wrong guess: choose repeat or coins
        steps.extend([
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Repeat the guess, 2 = Gain 2 coins",
                output_key="wndy_choice",
                number_options=[1, 2],
                is_mandatory=True,
                active_if_key="guess_wrong",
            ),
            CheckContextConditionStep(
                input_key="wndy_choice",
                operator="==",
                threshold=1,
                output_key="chose_repeat",
            ),
            CheckContextConditionStep(
                input_key="wndy_choice",
                operator="==",
                threshold=2,
                output_key="chose_coins",
            ),
            # Path A: gain coins
            GainCoinsStep(
                hero_key="guess_actor",
                amount=2,
                active_if_key="chose_coins",
            ),
        ])

        # Path B: repeat the full guess sequence (with prefixed keys)
        repeat_steps = _build_guess_steps(stats, consolation_coins=2, prefix="r")
        repeat_steps[0] = SetContextFlagStep(
            key="r_guess_actor", value=str(hero.id), active_if_key="chose_repeat",
        )
        # Gate all repeat steps on chose_repeat
        for step in repeat_steps:
            if not step.active_if_key:
                step.active_if_key = "chose_repeat"
        steps.extend(repeat_steps)

        return steps


# =============================================================================
# GET OVER HERE!
# =============================================================================


@register_effect("get_over_here")
class GetOverHereEffect(CardEffect):
    """
    Card Text: "Target a unit or a token in range and in a straight line,
    with no obstacles between you and the target. Move the target towards
    you in a straight line, until you are adjacent."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List["GameStep"]:
        return [
            # Store actor ID in context for ComputeHexStep
            SetContextFlagStep(key="goh_actor", value=str(hero.id)),
            # 1. Select target: in range, straight line, no obstacles between
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target a unit in range and in a straight line with no obstacles between you",
                output_key="goh_target",
                is_mandatory=True,
                filters=[
                    ExcludeIdentityFilter(exclude_self=True),
                    RangeFilter(max_range=stats.range),
                    InStraightLineFilter(),
                    ClearLineOfSightFilter(
                        blocked_by_units=False,
                        blocked_by_terrain=False,
                        blocked_by_obstacles=True,
                    ),
                ],
            ),
            # 2. Compute hex adjacent to actor along the line toward target
            #    origin=target, target=actor → direction from target toward actor
            #    scale=-1 → actor - direction = hex adjacent to actor toward target
            ComputeHexStep(
                origin_key="goh_target",
                target_key="goh_actor",
                scale=-1,
                output_key="goh_dest",
            ),
            # 3. Move target to that hex
            MoveUnitStep(
                unit_key="goh_target",
                destination_key="goh_dest",
                range_val=stats.range,
                is_movement_action=False,
            ),
        ]


# =============================================================================
# A COMPLICATED PROFESSION (Ultimate — Passive)
# =============================================================================


@register_effect("a_complicated_profession")
class AComplicatedProfessionEffect(CardEffect):
    """
    Card Text: "After you give a hero the Bounty marker, that hero discards
    a card, if able."

    Passive — fires automatically (not optional) whenever PlaceMarkerStep
    triggers AFTER_PLACE_MARKER.
    """

    def get_passive_config(self) -> Optional[PassiveConfig]:
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_PLACE_MARKER,
            uses_per_turn=0,  # Unlimited
            is_optional=False,
        )

    def get_passive_steps(
        self,
        state: "GameState",
        hero: "Hero",
        card: "Card",
        trigger: PassiveTrigger,
        context: Dict[str, Any],
    ) -> List[GameStep]:
        if trigger != PassiveTrigger.AFTER_PLACE_MARKER:
            return []

        target_id = context.get("marker_target_id")
        if not target_id:
            return []

        # Only triggers when placing Bounty marker on a hero
        from goa2.domain.types import HeroID as _HeroID

        victim = state.get_hero(_HeroID(str(target_id)))
        if not victim:
            return []

        return [ForceDiscardStep(victim_key="marker_target_id")]


