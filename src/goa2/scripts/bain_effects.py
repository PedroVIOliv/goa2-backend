from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CreateEffectStep,
    DiscardCardStep,
    GainCoinsStep,
    GameStep,
    GuessCardColorStep,
    MoveSequenceStep,
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
from goa2.domain.models.enums import CardContainerType, TargetType
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
# UNIMPLEMENTED EFFECTS — High-Level Design Notes
# =============================================================================

# -----------------------------------------------------------------------------
# GET OVER HERE! (Silver / Untiered) — MEDIUM
# Card Text: "Target a unit or a token in range and in a straight line, with
#   no obstacles between you and the target. Move the target towards you in a
#   straight line, until you are adjacent."
#
# HLD:
#   1. SelectStep(target_type="UNIT_OR_TOKEN",
#        filters=[RangeFilter(max_range=stats.range),
#                 InStraightLineFilter(),
#                 ClearLineOfSightFilter(blocked_by_units=False, blocked_by_obstacles=True)])
#      — "no obstacles" must use is_obstacle_for_actor (covers terrain, petrified
#        units, static barriers, etc.), NOT just is_terrain_hex. ClearLineOfSightFilter
#        currently checks is_terrain_hex — needs a new blocked_by_obstacles mode
#        that delegates to validator.is_obstacle_for_actor for intermediate hexes.
#   2. Since the filter already validates the entire straight-line path is
#      obstacle-free, we know the target can reach the hex adjacent to actor.
#      MoveUnitStep to move the target to the hex adjacent to Bain along the
#      line. The adjacent hex can be computed at build time or via a simple
#      context-based helper (actor_hex + normalize(target - actor)).
#
# Complexity: MEDIUM — needs ClearLineOfSightFilter update to support
#   is_obstacle_for_actor checking. No new steps needed; MoveUnitStep handles
#   the actual move. "Unit or token" targeting may need UnitTypeFilter
#   adjustments if tokens aren't normally targetable by SelectStep.
# New engine work: ClearLineOfSightFilter blocked_by_obstacles mode using
#   is_obstacle_for_actor.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# A GAME OF CHANCE (Blue / Tier I) — HARD (needs new mechanics)
# Card Text: "An enemy hero in radius with two or more cards in hand chooses
#   one of those cards. Guess that card's color, then reveal it.
#   If you guessed correctly, discard that card; otherwise you gain 1 coin.
#   (You can only guess colors that could be in that player's hand.)"
#
# HLD:
#   1. SelectStep(target_type="UNIT",
#        filters=[TeamFilter(ENEMY), RangeFilter(max_range=stats.radius),
#                 UnitTypeFilter(HERO), MinCardsInHandFilter(min=2)])
#      — need MinCardsInHandFilter (NEW) to enforce "two or more cards"
#   2. NEW: OpponentChooseCardStep — victim selects one of their hand cards
#      (input goes to victim, not actor). Sets context["chosen_card_id"].
#   3. NEW: GuessCardColorStep — actor guesses a color from valid options.
#      Must compute which colors COULD be in victim's hand (excluding the
#      chosen card? or including it?). Sets context["guessed_color"].
#   4. NEW: RevealAndResolveGuessStep — reveals the chosen card, compares
#      color to guess:
#        If correct: DiscardCardStep on victim for that specific card
#        If wrong: GainCoinsStep(amount=1) for actor
#
# Complexity: HIGH — requires 3+ new steps and 1 new filter. The "guess"
#   mechanic is unique to Bain and doesn't exist anywhere in the engine.
#   Key challenges:
#   - Input request targeting the VICTIM (not actor) for card choice
#   - Computing valid color guesses (colors present in victim's hand)
#   - The reveal/compare/branch logic
#   MinCardsInHandFilter is straightforward but new.
# New engine work: MinCardsInHandFilter, OpponentChooseCardStep,
#   GuessCardColorStep, RevealAndResolveGuessStep (+ StepTypes + unions).
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# DEAD MAN'S HAND (Blue / Tier II) — HARD
# Card Text: "An enemy hero in radius with two or more cards in hand chooses
#   one of those cards. Guess that card's color, then reveal it.
#   If you guessed correctly, discard that card; otherwise you gain 2 coins."
#
# HLD:
#   Identical to A Game of Chance but consolation prize is 2 coins instead of 1.
#   Can share implementation via parameterized helper:
#     _build_guess_card_color_steps(stats, consolation_coins=2)
#
# Complexity: Same as A Game of Chance (HIGH). Once the guess mechanic is built,
#   this is trivial.
# New engine work: Same as A Game of Chance (shared).
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# WE'RE NOT DONE YET! (Blue / Tier III) — VERY HARD
# Card Text: "An enemy hero in radius with two or more cards in hand chooses
#   one of those cards. Guess that card's color, then reveal it.
#   If you guessed correctly, discard that card; otherwise may repeat once
#   or gain 2 coins."
#
# HLD:
#   1-4. Same as Dead Man's Hand for the initial guess.
#   5. On WRONG guess: SelectStep(NUMBER, options=[1="repeat", 2="gain coins"])
#      Path A: MayRepeatOnceStep wrapping the entire guess sequence
#        (but must target a DIFFERENT card? Or same hero? — need rules clarification)
#      Path B: GainCoinsStep(amount=2)
#
# Complexity: VERY HIGH — builds on the guess mechanic (already hard) and adds
#   branching on failure with an optional repeat. The repeat needs to re-run
#   the full guess sequence. MayRepeatOnceStep exists but the "or gain coins"
#   alternative on the repeat prompt is non-standard — may need a custom
#   ChooseRepeatOrAlternativeStep.
# New engine work: Everything from A Game of Chance + conditional repeat-or-alt.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# DRINKING BUDDIES (Blue / Tier II) — MEDIUM
# Card Text: "You may have a hero in radius retrieve a discarded card.
#   If they do, you may also retrieve a discarded card."
#
# HLD:
#   1. SelectStep(target_type="UNIT", is_mandatory=False,
#        filters=[RangeFilter(max_range=stats.radius), UnitTypeFilter(HERO),
#                 TeamFilter(FRIENDLY)?, HasCardsInDiscardFilter()])
#      — "a hero" could mean any hero (friendly or enemy?) — likely friendly
#        based on card flavor. Need rules clarification.
#   2. For the target hero: SelectStep(target_type="CARD", container="DISCARD",
#        player_id=target_hero_id) — target picks a card from their discard
#   3. RetrieveCardStep(card_key="...") — target retrieves chosen card
#   4. Conditional on step 1 not being skipped:
#      SelectStep(target_type="CARD", container="DISCARD",
#        player_id=actor_id, is_mandatory=False)
#   5. RetrieveCardStep for actor
#
# Complexity: MEDIUM — RetrieveCardStep exists. The challenge is making a
#   NON-ACTOR hero select a card from their own discard (input goes to that
#   player). This "input for another player" pattern may need a player_id
#   override on SelectStep. Also the conditional "if they do" means actor's
#   retrieve is gated on target actually retrieving (skip_if_key pattern).
# New engine work: May need SelectStep player_id override for non-actor input.
#   Or use a SetActorStep to temporarily change actor. Check if precedent exists.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# ANOTHER ONE! (Blue / Tier III) — HARD
# Card Text: "You may have a hero in radius retrieve a discarded card.
#   If they do, you may also retrieve a discarded card.
#   End of turn: May repeat once."
#
# HLD:
#   Same as Drinking Buddies + MayRepeatOnceStep wrapping the whole sequence.
#   The "End of turn" timing is unusual — this doesn't happen immediately but
#   at end of Bain's turn (before FinalizeHeroTurnStep).
#
# Complexity: HARD — on top of Drinking Buddies' challenges, the "End of turn"
#   timing requires hooking into FinalizeHeroTurnStep or using a
#   DELAYED_TRIGGER effect (pattern exists in xargatha's FinalEmbraceEffect).
#   The repeat happens at end of turn, not immediately.
# New engine work: Same as Drinking Buddies + delayed trigger pattern.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# A COMPLICATED PROFESSION (Purple / Ultimate) — MEDIUM
# Card Text: "After you give a hero the Bounty marker, that hero discards a
#   card, if able." (Passive, always active)
#
# HLD:
#   get_passive_config() → PassiveConfig(
#     trigger=PassiveTrigger.AFTER_PLACE_MARKER,  # NEW trigger type?
#     is_optional=False,  # automatic, not a choice
#     uses_per_turn=unlimited,
#   )
#   get_passive_steps():
#     return [ForceDiscardStep(victim_key="marker_target_id")]
#
# Complexity: MEDIUM — the passive trigger "after you give a hero the Bounty
#   marker" doesn't map to any existing PassiveTrigger. Options:
#   a) Add PassiveTrigger.AFTER_PLACE_MARKER and trigger it from PlaceMarkerStep
#   b) Bake the discard directly into every Bain card that places a bounty
#      marker (simpler but duplicated).
#   Option (a) is cleaner. PlaceMarkerStep would need to check for passive
#   abilities after placing (similar to how AttackSequenceStep checks passives).
# New engine work: PassiveTrigger.AFTER_PLACE_MARKER + trigger hookup in
#   PlaceMarkerStep, OR inline the discard in each bounty-placing card.
# -----------------------------------------------------------------------------


# =============================================================================
# IMPLEMENTATION PRIORITY (suggested order)
# =============================================================================
#
# Phase 1 — Foundation (do first, unlocks many cards):
#   1. HasMarkerFilter (new filter) — needed by Hand Crossbow, Hunter-Seeker
#   2. Bounty defeat penalty in DefeatUnitStep — needed by Dead or Alive
#   3. Dead or Alive — simplest card, validates bounty marker flow
#   4. Narrow Escape — trivial defense card (PerfectGetaway + RemoveMarkerStep)
#   5. Close Call — defense + marker transfer to self
#   6. Vantage Point / High Ground — movement + obstacle ignoring (trivial)
#
# Phase 2 — Ranged attacks with bounty targeting:
#   7. Hand Crossbow — branching attack (bounty target OR adjacent)
#   8. Hunter-Seeker — both-targets variant
#
# Phase 3 — Card retrieval:
#   9. Drinking Buddies — retrieve mechanic (may need player_id on SelectStep)
#  10. Another One! — Drinking Buddies + delayed repeat
#
# Phase 4 — Guess mechanic (biggest new feature):
#  11. A Game of Chance — build entire guess infrastructure
#  12. Dead Man's Hand — reuses guess infra
#  13. We're Not Done Yet! — guess + repeat-or-alternative
#
# Phase 5 — Special:
#  14. Get Over Here! — needs ClearLineOfSightFilter obstacle mode
#  15. A Complicated Profession (Ultimate) — passive trigger on marker placement
