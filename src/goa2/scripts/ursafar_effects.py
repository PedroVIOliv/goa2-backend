from __future__ import annotations
from typing import List, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CreateEffectStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    GainCoinsStep,
    GameStep,
    MoveSequenceStep,
    SelectStep,
    SetContextFlagStep,
)
from goa2.engine.filters import (
    ImmunityFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models import (
    CardState,
    TargetType,
)
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


# =============================================================================
# SHARED HELPERS
# =============================================================================

def _has_ultimate(hero: Hero) -> bool:
    """Check if the ultimate card is in passive play."""
    return hero.ultimate_card is not None and hero.ultimate_card.state == CardState.PASSIVE


def is_enraged(hero: Hero, current_card: Card) -> bool:
    """Check if this hero is currently enraged.

    A hero is enraged if:
    - Any previously played card this round has is_active=True
      (excluding the current card being resolved)
    - OR the ultimate card is in passive play
    """
    if _has_ultimate(hero):
        return True
    for card in hero.played_cards:
        if card is None:
            continue
        if card.id == current_card.id:
            continue
        if card.is_active:
            return True
    return False



def _enraged_effect_step() -> CreateEffectStep:
    """Create the standard 'This round: You are enraged.' step."""
    return CreateEffectStep(
        effect_type=EffectType.ENRAGED,
        scope=EffectScope(
            shape=Shape.POINT,
            affects=AffectsFilter.SELF,
        ),
        duration=DurationType.THIS_ROUND,
        is_active=True,
    )


# =============================================================================
# GROUP A — Simple conditionals
# =============================================================================


# TIER II — BLUE: Cold Ire (MOVEMENT)
# "If enraged, gain +1 Movement. This round: You are enraged."
@register_effect("cold_ire")
class ColdIreEffect(CardEffect):
    """If enraged, gain +1 Movement. This round: You are enraged."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        bonus = 1 if is_enraged(hero, card) else 0
        return [
            MoveSequenceStep(unit_id=hero.id, range_val=stats.primary_value + bonus),
            _enraged_effect_step(),
        ]


# TIER III — BLUE: Eyes of Flame (MOVEMENT)
# "If enraged, gain +2 Movement. This round: You are enraged."
@register_effect("eyes_of_flame")
class EyesOfFlameEffect(CardEffect):
    """If enraged, gain +2 Movement. This round: You are enraged."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        bonus = 2 if is_enraged(hero, card) else 0
        return [
            MoveSequenceStep(unit_id=hero.id, range_val=stats.primary_value + bonus),
            _enraged_effect_step(),
        ]


# TIER II — RED: Rip (ATTACK)
# "Target a unit adjacent to you.
#  After the attack: If enraged, gain 1 coin.
#  This round: You are enraged."
@register_effect("rip")
class RipEffect(CardEffect):
    """Attack adjacent. If enraged, gain 1 coin. This round: You are enraged."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        steps: List[GameStep] = [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
        ]
        if is_enraged(hero, card):
            steps.extend([
                SetContextFlagStep(key="self_hero", value=hero.id),
                GainCoinsStep(hero_key="self_hero", amount=1),
            ])
        steps.append(_enraged_effect_step())
        return steps


# TIER I — GREEN: Sniff Out (SKILL, RANGED)
# "If enraged, an enemy hero in range discards a card, if able."
@register_effect("sniff_out")
class SniffOutEffect(CardEffect):
    """If enraged, an enemy hero in range discards a card, if able."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        if not is_enraged(hero, card):
            return []
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero in range to discard a card",
                output_key="victim_id",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                    ImmunityFilter(),
                ],
            ),
            ForceDiscardStep(victim_key="victim_id"),
        ]


# TIER II — GREEN: Eyes on the Prey (SKILL, RANGED)
# "If enraged, an enemy hero in range discards a card, if able."
@register_effect("eyes_on_the_prey")
class EyesOnThePreyEffect(SniffOutEffect):
    """If enraged, an enemy hero in range discards a card, if able."""
    pass


# TIER III — GREEN: Apex Predator (SKILL, RANGED)
# "If enraged, an enemy hero in range discards a card, or is defeated."
@register_effect("apex_predator")
class ApexPredatorEffect(CardEffect):
    """If enraged, an enemy hero in range discards a card, or is defeated."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        if not is_enraged(hero, card):
            return []
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero in range",
                output_key="victim_id",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                    ImmunityFilter(),
                ],
            ),
            ForceDiscardOrDefeatStep(victim_key="victim_id"),
        ]


# =============================================================================
# URSAFAR EFFECTS — HIGH-LEVEL DESIGN
# =============================================================================
#
# CORE MECHANIC: ENRAGED
# ----------------------
# Almost every Ursafar card says "This round: You are enraged."
# Some cards have "If enraged, ..." conditionals that gate bonus effects.
#
# Implementation:
#   - EffectType.ENRAGED in domain/models/effect.py
#   - Cards that SET enraged (red, blue, gold, silver) create an ActiveEffect
#     via CreateEffectStep(effect_type=EffectType.ENRAGED, duration=THIS_ROUND, ...)
#   - Cards that only CHECK enraged (all greens) do NOT create this effect
#   - This sets card.is_active = True (via EffectManager linkage)
#   - Helper function is_enraged() checks hero.played_cards for any is_active card
#     (excluding the current card being resolved), or if the ultimate is in play
#   - is_enraged() is called at build_steps time to conditionally include bonus steps
#
# def is_enraged(hero: Hero, current_card: Card) -> bool:
#     for card in hero.played_cards:
#         if card.id == current_card.id:
#             continue
#         if card.is_active:
#             return True
#     if hero.ultimate_card and hero.ultimate_card.state == CardState.PASSIVE:
#         return True
#     return False
#
# ULTIMATE MECHANIC: enraged_active_override on Card
# ----------------------------------------------------
# "All your resolved cards count as active" — the ultimate sets
# card.enraged_active_override = True on ALL of the hero's cards.
# The Card.is_active property returns (is_active_base or enraged_active_override),
# so card.is_active always reads True — for our effects, other heroes' effects,
# filters, views, anything. EffectManager is unchanged; it writes to is_active
# (which hits the setter on is_active_base), but the getter always wins.
# Angry Roar can just check card.is_active directly — no special helper needed.
#
#
# =============================================================================
# CARD EFFECTS BY TIER
# =============================================================================
#
# UNTIERED — GOLD: Claws That Catch (ATTACK)
# --------------------------------------------
# "Before the attack: If enraged, you may move 1 space to a space adjacent
#  to an enemy hero. Target a unit adjacent to you.
#  This round: You are enraged."
#
# Steps:
#   if is_enraged:
#     MoveSequenceStep(range=1, filters=[AdjacencyFilter(to enemy hero)])  (optional)
#   AttackSequenceStep(damage, range=1)
#   CreateEffectStep(ENRAGED, THIS_ROUND)
#
# Reference: Brogan's Mad Dash (movement before attack)
#
#
# UNTIERED — SILVER: Angry Roar (SKILL)
# ---------------------------------------
# "If enraged, perform the primary action on one of your active cards
#  with an active effect.
#  This round: You are enraged."
#
# Steps:
#   if is_enraged:
#     SelectStep(target_type=CARD, filters=[active cards with active effects])
#     PerformPrimaryActionStep(card_key=...) — NEW STEP needed
#   CreateEffectStep(ENRAGED, THIS_ROUND)
#
# Note: Needs a new step to perform the primary action of a selected card.
#       Primary actions are ATTACK (with value), MOVEMENT (with value), or SKILL.
#       This step reads the selected card's primary_action and primary_action_value,
#       then pushes the appropriate sub-steps (AttackSequenceStep or MoveSequenceStep).
#       Just check card.is_active — the enraged_active_override handles the ultimate.
#
#
# TIER I — RED: Prey Drive (ATTACK)
# -----------------------------------
# "Target a unit adjacent to you.
#  After the attack: If enraged, and the target was not removed,
#  remove up to 1 enemy minion in radius.
#  This round: You are enraged."
#
# Steps:
#   AttackSequenceStep(damage, range=1)
#   if is_enraged:
#     CheckContextConditionStep(target not removed)
#     SelectStep(UNIT, filters=[MINION, ENEMY, RangeFilter(radius)], max=1, optional)
#     RemoveUnitStep(unit_key=...)
#   CreateEffectStep(ENRAGED, THIS_ROUND)
#
# Reference: Sabina's Shootout (attack + conditional minion removal)
#
#
# TIER I — BLUE: Prowling Brute (MOVEMENT)
# ------------------------------------------
# "If enraged, after movement, you may swap with a unit or a token
#  adjacent to you.
#  This round: You are enraged."
#
# Steps:
#   MoveSequenceStep(range=primary_value)
#   if is_enraged:
#     SelectStep(UNIT, filters=[AdjacencyFilter], optional)
#     SwapUnitsStep(hero, selected_unit)
#   CreateEffectStep(ENRAGED, THIS_ROUND)
#
# Reference: Sabina's Back to Back (swap with adjacent unit)
#
#
# TIER I — GREEN: Sniff Out (SKILL, RANGED)  [IMPLEMENTED]
# -------------------------------------------
# "If enraged, an enemy hero in range discards a card, if able."
#
# Reference: Sabina's Close Support (force discard if able)
#
#
# =============================================================================
# TIER II
# =============================================================================
#
# TIER II — RED: Rip (ATTACK)  [IMPLEMENTED]
# -----------------------------
# "Target a unit adjacent to you.
#  After the attack: If enraged, gain 1 coin.
#  This round: You are enraged."
#
# Reference: Sabina's War Drummer (conditional coin gain)
#
#
# TIER II — RED: Prey Abundance (ATTACK)
# ----------------------------------------
# "Target a unit adjacent to you.
#  After the attack: If enraged, and the target was not removed,
#  remove up to 1 enemy minion in radius.
#  This round: You are enraged."
#
# Steps: Same pattern as Prey Drive (Tier I red) with different stats.
#
#
# TIER II — BLUE: Cold Ire (MOVEMENT)  [IMPLEMENTED]
# --------------------------------------
# "If enraged, gain +1 Movement.
#  This round: You are enraged."
#
#
# TIER II — BLUE: Rampaging Beast (MOVEMENT)
# --------------------------------------------
# "If enraged, after movement, you may swap with a unit or a token
#  adjacent to you; if you do, move up to 1 additional space.
#  This round: You are enraged."
#
# Steps:
#   MoveSequenceStep(range=primary_value)
#   if is_enraged:
#     SelectStep(UNIT, filters=[AdjacencyFilter], optional)
#     SwapUnitsStep(hero, selected_unit)
#     MoveSequenceStep(range=1, optional)  — only if swap happened
#   CreateEffectStep(ENRAGED, THIS_ROUND)
#
# Reference: Sabina's Back to Back + Prowling Brute pattern extended
#
#
# TIER II — GREEN: Instinctive Reaction (SKILL)
# ------------------------------------------------
# "If enraged, choose one —
#  - Perform the primary action on one of your discarded cards.
#  - You may retrieve a discarded card."
#
# Steps:
#   if is_enraged:
#     SelectStep(CHOOSE_ACTION, options=["perform_primary", "retrieve"])
#     Branch A: SelectStep(CARD, discard) → PerformPrimaryActionStep (NEW STEP)
#     Branch B: SelectStep(CARD, discard) → RetrieveCardStep
#   (NO enraged set — green cards only check, never set)
#
# Note: Needs CHOOSE_ACTION + branching pattern.
# Reference: Sabina's Steady Advance (card retrieval from discard)
#
#
# TIER II — GREEN: Eyes on the Prey (SKILL, RANGED)  [IMPLEMENTED]
# ---------------------------------------------------
# "If enraged, an enemy hero in range discards a card, if able."
#
# Steps: Same pattern as Sniff Out (Tier I green) with different stats.
#   (NO enraged set — green cards only check, never set)
#
#
# =============================================================================
# TIER III
# =============================================================================
#
# TIER III — RED: Tear (ATTACK)
# -------------------------------
# "Target a unit adjacent to you.
#  After the attack: If enraged, gain 2 coins;
#  if you defeated a hero, that hero spends 1 additional Life counter.
#  This round: You are enraged."
#
# Steps:
#   AttackSequenceStep(damage, range=1)
#   if is_enraged:
#     GainCoinsStep(hero_key, amount=2)
#     CheckHeroDefeatedThisRoundStep(...)
#     SpendLifeCounterStep(victim_key=...) — NEW STEP or reuse existing defeat logic
#   CreateEffectStep(ENRAGED, THIS_ROUND)
#
# Note: "Spends 1 additional Life counter" is a unique mechanic. Need to check
#       if there's existing support or if a new step is needed.
# Reference: Sabina's War Drummer (coin gain), Brogan's defeat checks
#
#
# TIER III — RED: Feeding Frenzy (ATTACK)
# -----------------------------------------
# "Target a unit adjacent to you.
#  After the attack: If enraged, and the target was not removed,
#  remove up to 2 enemy minions in radius.
#  This round: You are enraged."
#
# Steps: Same pattern as Prey Drive/Prey Abundance but max=2 minions.
#
# Reference: Sabina's Bullet Hell (multi-select minion removal)
#
#
# TIER III — BLUE: Eyes of Flame (MOVEMENT)  [IMPLEMENTED]
# -------------------------------------------
# "If enraged, gain +2 Movement.
#  This round: You are enraged."
#
#
# TIER III — BLUE: Unstoppable Force (MOVEMENT)
# ------------------------------------------------
# "If enraged, after movement, you may swap with a unit or a token
#  adjacent to you; if you do, move up to 2 additional spaces.
#  This round: You are enraged."
#
# Steps: Same pattern as Rampaging Beast but 2 additional spaces.
#
#
# TIER III — GREEN: Evolutionary Response (SKILL)
# -------------------------------------------------
# "If enraged, choose one, or both —
#  - Perform the primary action on one of your discarded cards.
#  - You may retrieve a discarded card."
#
# Steps:
#   if is_enraged:
#     SelectStep(CHOOSE_ACTION, options=["perform_primary", "retrieve", "both"])
#     Branch A: SelectStep(CARD, discard) → PerformPrimaryActionStep
#     Branch B: SelectStep(CARD, discard) → RetrieveCardStep
#     Branch C: Both A then B
#   (NO enraged set — green cards only check, never set)
#
# Note: "Choose one, or both" is the Tier III upgrade of Instinctive Reaction's
#       "choose one". Same mechanic, expanded choice.
#
#
# TIER III — GREEN: Apex Predator (SKILL, RANGED)  [IMPLEMENTED]
# -------------------------------------------------
# "If enraged, an enemy hero in range discards a card, or is defeated."
#
# Reference: Sabina's Covering Fire (discard or defeat)
#
#
# =============================================================================
# ULTIMATE (PURPLE/TIER IV): Unbound Fury (PASSIVE)
# =============================================================================
#
# "You are always enraged, and all your resolved cards count as active."
#
# Implementation:
#   - is_enraged() checks _has_ultimate(hero) first → returns True immediately
#   - On ultimate activation, set card.enraged_active_override = True on ALL
#     of the hero's cards (deck, hand, played, discard). The Card.is_active
#     property returns (is_active_base or enraged_active_override), so
#     card.is_active always reads True for every card. EffectManager unchanged.
#   - This affects Angry Roar, other heroes' effect checks, views — everything.
#
#
# =============================================================================
# EFFECT TIERS / IMPLEMENTATION ORDER
# =============================================================================
#
# Shared foundation (implement first):  [DONE]
#   1. EffectType.ENRAGED in domain/models/effect.py
#   2. is_enraged() helper in this file
#   3. enraged_active_override field on Card model
#   4. _enraged_effect_step() helper in this file
#
# Group A — Simple conditionals (easiest, no new steps):  [DONE]
#   - Cold Ire / Eyes of Flame (movement bonus)
#   - Rip (attack + coin gain) — Tear uses same pattern + extra defeat logic
#   - Sniff Out / Eyes on the Prey (force discard if able)
#   - Apex Predator (force discard or defeat)
#
# Group B — Attack + conditional minion removal:
#   - Prey Drive / Prey Abundance / Feeding Frenzy
#
# Group C — Movement + swap + additional movement:
#   - Prowling Brute / Rampaging Beast / Unstoppable Force
#
# Group D — Pre-attack movement:
#   - Claws That Catch
#
# Group E — Needs new steps or patterns:
#   - Instinctive Reaction / Evolutionary Response (PerformPrimaryActionStep)
#   - Angry Roar (perform primary action of active card — just checks card.is_active)
#   - Tear's "spend 1 additional Life counter" (SpendLifeCounterStep?)
#
# Group F — Ultimate:
#   - Unbound Fury (always enraged + enraged_active_override on all cards)
#
# =============================================================================
