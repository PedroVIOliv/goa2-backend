from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    GameStep,
    SetContextFlagStep,
)
from goa2.engine.filters import (
    ClearLineOfSightFilter,
    InStraightLineFilter,
    RangeFilter,
    TeamFilter,
)
from goa2.domain.models.marker import MarkerType

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


# =============================================================================
# UNIMPLEMENTED EFFECTS — High-Level Design Notes
# =============================================================================

# -----------------------------------------------------------------------------
# DEAD OR ALIVE (Gold / Untiered) — EASY
# Card Text: "Target a unit adjacent to you.
#   After the attack: You may give an enemy hero in play the Bounty marker.
#   A hero with the Bounty marker spends 1 additional Life counter when defeated."
#
# HLD:
#   1. AttackSequenceStep(damage=stats.primary_value) — standard adjacent attack
#   2. SelectStep(target_type="UNIT", is_mandatory=False,
#        filters=[TeamFilter(relation="ENEMY"), UnitTypeFilter(unit_type="HERO")])
#      — optional, select any enemy hero in play (not just in radius/range)
#   3. PlaceMarkerStep(marker_type=MarkerType.BOUNTY, target_key="...", value=0)
#
# Complexity: LOW — all steps exist. PlaceMarkerStep handles singleton
#   semantics (auto-removes from previous holder). The "extra life counter"
#   penalty needs to be checked in DefeatUnitStep or life-counter logic —
#   verify that defeat handling reads the BOUNTY marker. If not, that's the
#   only new work needed (small change in DefeatUnitStep).
# -----------------------------------------------------------------------------

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
# HAND CROSSBOW (Red / Tier II) — EASY
# Card Text: "Choose one — • Target a hero in range with a Bounty marker.
#   • Target a unit adjacent to you."
#
# HLD:
#   1. SelectStep(target_type="NUMBER", options for choice 1 or 2)
#   2. CheckContextConditionStep → branch:
#      Path A (bounty target): AttackSequenceStep with filters:
#        [RangeFilter, BountyMarkerFilter (NEW or inline check),
#         UnitTypeFilter(HERO)]
#      Path B (adjacent): AttackSequenceStep(damage=...) — standard melee
#
# Complexity: LOW-MEDIUM — the branching pattern exists (see ThrowingAxeEffect
#   in brogan_effects.py). The main question is filtering for "has Bounty marker".
#   Options: (a) new HasMarkerFilter, (b) build target list at effect build time
#   and pass as allowed_ids. Option (b) is simpler but less robust if marker
#   moves mid-stack. A small HasMarkerFilter(marker_type=BOUNTY) would be clean
#   and reusable across all Bain cards.
# New engine work: HasMarkerFilter + FilterType + AnyFilter union (small).
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# HUNTER-SEEKER (Red / Tier III) — MEDIUM
# Card Text: "Choose one, or both, on different targets —
#   • Target a hero in range with a Bounty marker.
#   • Target a unit adjacent to you."
#
# HLD:
#   Same branching as Hand Crossbow but with THREE paths:
#   1. SelectStep(target_type="NUMBER", options: [1=bounty only, 2=adjacent only, 3=both])
#   2. Path "bounty only": AttackSequenceStep with bounty+range filters
#      Path "adjacent only": AttackSequenceStep with adjacency
#      Path "both": Two AttackSequenceSteps sequenced, with ExcludeIdentityFilter
#        on the second to ensure "different targets".
#
# Complexity: MEDIUM — the "both on different targets" requires two sequential
#   attacks where the second excludes the first target. Pattern exists in
#   MiddlefingerOfDeathEffect (dodger). Needs HasMarkerFilter (same as Hand Crossbow).
# New engine work: HasMarkerFilter (shared with Hand Crossbow).
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# CLOSE CALL (Green / Tier I) — MEDIUM (needs marker transfer logic)
# Card Text: "If a hero in play has a Bounty marker, block the attack and that
#   hero gives the marker to you. (The marker's effect is applied to you.)"
#
# HLD:
#   build_defense_steps:
#     if _bounty_marker_in_play(state):
#       return [
#         SetContextFlagStep(key="auto_block", value=True),
#         PlaceMarkerStep(marker_type=BOUNTY, target_id=defender.id, value=0)
#       ]
#     else:
#       return [SetContextFlagStep(key="defense_invalid", value=True)]
#
# Complexity: LOW-MEDIUM — similar to PerfectGetawayEffect. The marker transfer
#   is just PlaceMarkerStep on self (Bain), which auto-removes from previous
#   holder (singleton semantics). The "marker's effect is applied to you" means
#   Bain now spends +1 life counter if defeated — same defeat penalty logic
#   needed for Dead or Alive.
# New engine work: None if Dead or Alive's defeat penalty is already done.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# NARROW ESCAPE (Green / Tier II) — EASY
# Card Text: "If a hero in play has a Bounty marker, block the attack and
#   retrieve the marker."
#
# HLD:
#   build_defense_steps:
#     if _bounty_marker_in_play(state):
#       return [
#         SetContextFlagStep(key="auto_block", value=True),
#         RemoveMarkerStep(marker_type=MarkerType.BOUNTY)
#       ]
#     else:
#       return [SetContextFlagStep(key="defense_invalid", value=True)]
#
# Complexity: LOW — identical pattern to PerfectGetaway + RemoveMarkerStep.
#   RemoveMarkerStep already exists and returns marker to supply.
# New engine work: None.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# VANTAGE POINT (Green / Tier II) — EASY
# Card Text: "Ignore obstacles. If a hero in play has a Bounty marker,
#   +1 movement."
#
# HLD:
#   movement_value = stats.primary_value  # base 2
#   if _bounty_marker_in_play(state):
#       movement_value += 1
#   return [
#     MoveSequenceStep(range_val=movement_value, pass_through_obstacles=True)
#   ]
#
# Complexity: LOW — MoveSequenceStep supports pass_through_obstacles=True.
#   Conditional bonus is a simple build-time check (bounty in play).
# New engine work: None.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# HIGH GROUND (Green / Tier III) — EASY
# Card Text: "Ignore obstacles. If a hero in play has a Bounty marker,
#   +2 movement."
#
# HLD:
#   Same as Vantage Point but +2 instead of +1. Can share a helper:
#   _build_movement_ignore_obstacles(stats, bonus=2)
# Complexity: LOW — identical pattern.
# New engine work: None.
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
