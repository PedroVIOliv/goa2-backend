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
#   - New EffectType.ENRAGED in domain/models/effect.py
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
# TIER I — GREEN: Sniff Out (SKILL, RANGED)
# -------------------------------------------
# "If enraged, an enemy hero in range discards a card, if able."
#
# Steps:
#   if is_enraged:
#     SelectStep(UNIT, filters=[HERO, ENEMY, RangeFilter(range)])
#     ForceDiscardStep(victim_key=...)
#   (NO enraged set — green cards only check, never set)
#
# Reference: Sabina's Close Support (force discard if able)
#
#
# =============================================================================
# TIER II
# =============================================================================
#
# TIER II — RED: Rip (ATTACK)
# -----------------------------
# "Target a unit adjacent to you.
#  After the attack: If enraged, gain 1 coin.
#  This round: You are enraged."
#
# Steps:
#   AttackSequenceStep(damage, range=1)
#   if is_enraged:
#     GainCoinsStep(hero_key, amount=1)
#   CreateEffectStep(ENRAGED, THIS_ROUND)
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
# TIER II — BLUE: Cold Ire (MOVEMENT)
# --------------------------------------
# "If enraged, gain +1 Movement.
#  This round: You are enraged."
#
# Steps:
#   if is_enraged:
#     MoveSequenceStep(range=primary_value + 1)
#   else:
#     MoveSequenceStep(range=primary_value)
#   CreateEffectStep(ENRAGED, THIS_ROUND)
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
# TIER II — GREEN: Eyes on the Prey (SKILL, RANGED)
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
# TIER III — BLUE: Eyes of Flame (MOVEMENT)
# -------------------------------------------
# "If enraged, gain +2 Movement.
#  This round: You are enraged."
#
# Steps: Same pattern as Cold Ire but +2 instead of +1.
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
# TIER III — GREEN: Apex Predator (SKILL, RANGED)
# -------------------------------------------------
# "If enraged, an enemy hero in range discards a card, or is defeated."
#
# Steps:
#   if is_enraged:
#     SelectStep(UNIT, filters=[HERO, ENEMY, RangeFilter(range)])
#     ForceDiscardOrDefeatStep(victim_key=...)
#   (NO enraged set — green cards only check, never set)
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
#   - is_enraged() already checks ultimate_card.state == PASSIVE → returns True
#   - "Resolved cards count as active" means effects from resolved cards
#     should not be deactivated at end of round. This may require:
#     Option A: Override effect expiration for this hero's effects
#     Option B: Re-activate effects at round start via passive trigger
#   - Likely needs a PassiveConfig with a trigger (e.g. ROUND_START) that
#     re-activates all resolved card effects, or a flag that prevents
#     expiration of THIS_ROUND effects for this hero.
#
# Note: This is the most complex piece. "Resolved cards count as active" affects
#       Angry Roar (which targets "active cards with active effects") and possibly
#       other interactions. Needs careful design during implementation.
#
#
# =============================================================================
# EFFECT TIERS / IMPLEMENTATION ORDER
# =============================================================================
#
# Shared foundation (implement first):
#   1. EffectType.ENRAGED in domain/models/effect.py
#   2. is_enraged() helper in this file
#   3. CreateEffectStep(ENRAGED) pattern — used by every card
#
# Group A — Simple conditionals (easiest, no new steps):
#   - Cold Ire / Eyes of Flame (movement bonus)
#   - Rip / Tear (attack + coin gain)
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
#   - Angry Roar (perform primary action of active card)
#   - Tear's "spend 1 additional Life counter" (SpendLifeCounterStep?)
#
# Group F — Ultimate:
#   - Unbound Fury (always enraged + resolved-as-active)
#
# =============================================================================
