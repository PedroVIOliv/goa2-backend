# Cutter — Card Effect Test Specification

Test plan for all 17 Cutter effects (deck + ultimate). Each family lists the
scenarios we validate **positively** (what it must do) and **negatively** (what
it must not do). `✓` marks scenarios already implemented and passing in
`tests/engine/effects/cases/test_cutter_effects.py`.

Locked interpretations live in the `project-cutter-design-decisions` memory.
Tests use the fluent `EffectScenarioBuilder` + `run_card` pattern.

> **Status: COMPLETE.** All 18 effects (17 deck + ultimate) are implemented in
> `src/goa2/scripts/cutter_effects.py` with coverage in
> `tests/engine/effects/cases/test_cutter_effects.py` (38 tests). The `✓` marks
> below predate completion; every family listed here is now implemented and green.

## Conventions / global rules

- **Coins** = `hero.gold` (gained via `GainCoinsStep`, `GOLD_GAINED` event).
- **No `auto_select_if_one`** on any Cutter selection — always prompt, even with a
  single candidate.
- **Immunity:** `SelectStep` offensive targeting excludes immune units by default.
  `CountMatchFilter` presence checks do **not** filter immunity (they count immune
  units), per the rule "presence checks count immune units."
- **Mandatory vs optional:** only "you may" / "up to" / "if able" are optional;
  everything else is mandatory. A failed mandatory step stops and skips the rest.

### Cross-cutting principle: bound vs. independent steps

Punctuation determines linkage:

- **Same sentence → bound.** Every part must be able to happen; a destination/target
  is only legal if the whole sentence can resolve (e.g. Brace's "move ... adjacent to
  an enemy hero; that hero discards" — landing next to an *immune* hero is illegal
  because the discard can't occur).
- **Separate sentences (`MOVE. ATTACK.`) → independent.** The first resolves on its
  own; the second is a conditional follow-up that may simply not happen (e.g. the
  charge cards' move is committed even when no attack target ends up ahead).

---

## 1. Bombardment / Barrage / Broadside — force discard in radius

> "An enemy hero in radius, adjacent to another enemy unit and not adjacent to you,
> discards a card, if able." (Broadside: "May repeat once on a different target.")
> Radius: Bombardment 3, Barrage 4, Broadside 4.

**Should do**
- ✓ Eligible enemy hero (in radius, not adjacent to Cutter, flanked by another enemy
  unit) is forced to discard a card of *their* choice.
- ✓ Adjacency presence check counts an **immune** flanking minion.
- ✓ Broadside repeats once on a **different** hero.
- Radius scales: a hero at distance 4 is targetable by Barrage/Broadside, not Bombardment.
- Victim with several cards picks which to discard.

**Should NOT do**
- ✓ Target a hero adjacent to Cutter (min range 2).
- ✓ Target an isolated hero (no adjacent enemy unit).
- Target a hero outside radius.
- Count a flanking unit friendly to Cutter (the "other enemy unit" must be Cutter's enemy).
- Target/affect a friendly hero.
- Broadside: re-hit the same hero on the repeat.
- Hero with an empty hand → no discard, **no defeat** ("if able"), no error.
- No eligible target → resolves with no prompt, no crash.

## 2. Brace for Impact / Ramming Speed / Crashland — charge-through, discard

> "Move 3 / 3–4 / 3–4–5 spaces in a straight line, ignoring obstacles, to a space
> adjacent to an enemy hero; that hero discards a card, if able."

*Bound sentence:* landing must enable the discard.

**Should do**
- Move in a straight line **through an obstacle** and land adjacent to a non-immune
  enemy hero, who then discards.
- Distance options honored: Brace exactly 3; Ramming 3 or 4; Crashland 3/4/5.
- If the landing hex is adjacent to two enemy heroes, **Cutter chooses** which discards.

**Should NOT do**
- Treat a hex as a valid landing because it is adjacent only to an **immune** enemy hero.
- Land adjacent to only an enemy **minion** (hero-specific).
- Land on an occupied/obstacle hex (final hex must be empty).
- Land off the straight line, or below min / above max distance.
- Proceed at all if no legal charge destination exists (mandatory move → whole action skips).
- Defeat a hero with an empty hand (discard is "if able", not "or defeated").

## 3. Daring Strike / Bold Thrust / Fearless Lunge — modal charge attack

> "Choose one — • Before the attack: Move 1 / 1–2 / 1–3 in a straight line. Target a
> hero adjacent to you in the direction of the move; +2 Attack. • Target a unit
> adjacent to you."

*Separate sentences:* in branch A the move is committed independently of the attack.
**Both branches always offered.**

**Branch A flow:** choose straight-line destination (≥1) → move (committed) → if a hero
is adjacent in the move direction, +2 attack; else move stands, no attack.

**Should do**
- Move, then +2-attack a collinear hero ahead (combat `attack_value` = base + 2).
- Move into open space with **no hero ahead** → move kept, no attack, no error.
- Reach scales: Daring move 1, Bold ≤2, Fearless ≤3.
- Branch B: attack any enemy unit (hero or minion) adjacent to Cutter, base damage.

**Should NOT do**
- Undo/forbid the move because no valid attack target exists.
- Branch A: attack a hero off the move axis, or a minion.
- Branch B: apply +2, or hit a non-adjacent unit.
- Perform both branches.

## 4. Evasive Shot / Tumble Shot — ranged straight-line attack + retreat

> "Target a unit in range and in a straight line. After the attack: Move up to 2 / 3
> spaces in the opposite direction." Range 2.

**Should do**
- Ranged attack (range 2) at a unit in a straight line; `is_ranged` set.
- After the attack, move up to N in the **opposite** direction (away from target, same axis).
- Retreat happens even if the target was defeated.

**Should NOT do**
- Target a unit off-axis or out of range.
- Retreat toward the target or sideways (opposite axis only).
- Be forced to move (it is "up to" → may move 0 / partial).
- Move through an obstacle / off the map during retreat (stops, no crash).

## 5. Outmaneuver / Outsmart — swap + nudge

> "Swap with an enemy minion in radius; you may move that minion up to 2 / 3 spaces."
> Radius 3.

**Should do**
- Swap Cutter's hex with an enemy minion in radius.
- Then optionally move that minion up to N spaces (Cutter controls); may move 0.

**Should NOT do**
- Swap with a hero, a friendly minion, or a minion out of radius.
- Swap with an immune minion (offensive target → immunity applies).
- Nudge Cutter instead of the minion.
- Proceed if no enemy minion in radius (swap is mandatory → skip).

## 6. X Marks the Spot / A Fistful of Coins — enemy chooses

> "An enemy hero in radius chooses one — • You place that hero in a space in radius.
> • You gain 2 / 3 coins." (Fistful: "If you have 13+ coins, you alone win the game.")
> Radius 3.

**Should do**
- Cutter picks an enemy hero in radius; **that hero's player** chooses A or B.
- A → Cutter places the hero on an empty hex in radius.
- B → Cutter gains 2 (X) / 3 (Fistful) coins.
- Fistful at ≥13 coins after choosing the coin option → Cutter wins alone and the game ends immediately.

**Should NOT do**
- Target a minion / friendly / out-of-radius hero.
- Let Cutter make the A/B choice (must be the enemy hero's player).
- Place onto an occupied/obstacle hex or outside radius.
- Trigger the win below 13 coins, or when the enemy chooses the placement option.

## 7. Grappling Bolt — pull self to an obstacle

> "Target an obstacle in range and in a straight line, with no obstacles between you;
> ignore immunity. Move in a straight line towards that obstacle until you are adjacent
> to it." Range 5 (silver basic SKILL).

**Target = any obstacle: terrain, token, unit, or turret.** No board-edge concept —
every tile is terrain-or-not, and "edge" tiles are terrain and are valid anchors.

**Should do**
- Target an obstacle within range 5, in a straight line, with a clear path; pull Cutter
  along the line until adjacent.
- Ignore immunity: an immune heavy minion is a legal anchor.
- Terrain anchors (including map-boundary terrain) are valid.

**Should NOT do**
- Target an obstacle off-axis, out of range, or with another obstacle between.
- Target an empty / non-obstacle hex.
- Land on the obstacle (stops adjacent); if already adjacent, move 0.

## 8. Walk the Plank — modal push / defeat

> "Choose one — • Push an enemy hero adjacent to you up to 4 spaces; if that hero is
> pushed into another zone, that hero discards a card, or is defeated. • Defeat a
> minion adjacent to you." Gold basic SKILL. **Both branches always offered.**

**Should do**
- A: push an adjacent enemy hero up to 4; if it ends in a different zone (`zone_id`
  changes), it discards, **or is defeated** (defeated if no cards).
- B: defeat an adjacent enemy minion (Cutter gains coins).

**Should NOT do**
- A: push a non-adjacent / non-hero target.
- A: trigger discard-or-defeat when the push stays in the same zone.
- B: defeat a friendly minion, a hero, a non-adjacent minion, or an **immune** minion.
- Perform both branches.

## 9. Legend of the Skies (ultimate) — re-perform previous turn slot

> "The first time each turn after you perform a primary action, you may perform the
> primary action of a card in the previous turn slot."

Trigger: `AFTER_RESOLVE_CARD`, `uses_per_turn=1`. Previous slot =
`played_cards[resolved_turn_count-1]` (current card not yet moved into played_cards).

**Should do**
- On turn ≥2 of a round, after the current card resolves, offer re-performing the
  primary action of the immediately previous slot's card.
- Re-run that card's full primary effect; optional (may decline); once per turn.

**Should NOT do**
- Offer on the first turn of a round (no previous slot).
- Offer when the previous slot is empty (card discarded/removed).
- Re-perform the current card instead of the previous one.
- Trigger when the ultimate is not active.
