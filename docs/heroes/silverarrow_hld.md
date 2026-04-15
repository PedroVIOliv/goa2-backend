# Silverarrow: High-Level Design

## Overview

Silverarrow is a ranged archer / skirmisher themed around long-range picking, root/slow zones, and self-mobility. Her kit revolves around:

- **Red line (Clear / Opportunity / Snap Shot)**: Long-range snipe that requires an *isolated* target (not adjacent to any other unit), with a melee fallback.
- **Red line (Rain / Long Shot)**: Maximum-range shot that chains extra shots on hero hits (Tier III only).
- **Blue line (Grappling Branches / Entangling Vines / Grasping Roots)**: Movement-restriction auras (identical to Arien's Deluge).
- **Blue line (Treetop Sentinel / Warning Shot)**: End-of-turn forced discard-or-defeat in radius.
- **Green line (Lead Astray / Divert Attention / Disorient)**: Pull an adjacent enemy, then mirror-move yourself in a straight line.
- **Green line (Nature's Blessing / Fae Healing)**: Gift-retrieve — let a friendly hero retrieve a discarded card and gain coins.
- **Untiered Gold (Shoot and Scoot)**: Max-range shot + fast-travel escape.
- **Untiered Silver (Trailblazer)**: Self fast travel + round-long friendly ignore-obstacles aura.
- **Ultimate (Wild Hunt)**: Before every action, may move 2 spaces in a straight line.

Most primitives already exist; three items need new infra: a "not adjacent to any other unit" filter, a friendly ignore-obstacles zone effect, and a `BEFORE_ACTION` passive trigger.

---

## Card Family Analysis

### Family 1: Isolated-Target Snipe — RED (Clear Shot / Opportunity Shot / Snap Shot)

**Effect text:** "Choose one — Target a unit in range, which is not adjacent to any other unit. / Target a unit adjacent to you."

**Implementation:** Pure `AttackSequenceStep`. The base step already injects `RangeFilter(max_range=effective_range)` as its built-in range gate (`steps.py:5291-5295`), so we only need to add the "isolated OR melee fallback" disjunction via `target_filters`:

```python
AttackSequenceStep(
    damage=stats.primary_value,
    range_val=stats.range,
    target_filters=[
        OrFilter(filters=[
            # Long-range branch: target has zero other units adjacent to it.
            CountMatchFilter(
                sub_filters=[
                    RangeFilter(
                        min_range=1, max_range=1,
                        origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY,
                    ),
                ],
                max_count=0,
            ),
            # Melee fallback: target is adjacent to shooter.
            RangeFilter(max_range=1),
        ]),
    ],
)
```

**How the isolation check works:** `CountMatchFilter` iterates every unit currently on the board (not hexes — entity IDs in `state.entity_locations`), publishes the candidate target's hex under `_cmf_origin_hex`, and counts units for which the inner `RangeFilter(min=1, max=1)` passes — i.e., units standing on a hex at topology-distance exactly 1 from the candidate. `max_count=0` requires that number to be zero. Notes:

- `min_range=1` excludes the candidate from its own count (distance 0 to itself), so no `ExcludeIdentityFilter` is needed.
- Tokens are naturally excluded (`get_unit() is None` branch inside `CountMatchFilter`).
- Topology distance respects split reality automatically.
- The shooter herself counts as "another unit" — if she is adjacent to the target, the long-range branch fails and the `RangeFilter(max_range=1)` branch handles the case. That matches the card text.

**Tiny engine extension:** `CountMatchFilter.apply()` today rejects non-`Hex` candidates (it was built for Misa's `swoop_in` place-self-adjacent-to-2+-enemies, which selects a HEX). Generalize it to also accept string entity-ID candidates: when `candidate` is a string, resolve `state.entity_locations[BoardEntityID(candidate)]` → hex, then proceed with the existing publish-and-iterate logic. ~5 lines. Misa's existing hex-candidate usage is untouched.

**Difficulty: TRIVIAL** — no new filter class, no enum additions, just a small generalization of an existing filter's accepted candidate shape.

**Existing pieces:** `AttackSequenceStep`, `OrFilter`, `CountMatchFilter`, `RangeFilter(origin_hex_key)`, `TeamFilter`, `ImmunityFilter`.
**New pieces:** None.
**Engine changes:** `CountMatchFilter.apply()` accepts unit-ID string candidates in addition to hex candidates.

---

### Family 2: Maximum-Range Snipe — RED (Long Shot / Rain of Arrows)

**Long Shot (II):** "Target a unit at maximum range."
**Rain of Arrows (III):** "Target a unit at maximum range. If you target a hero, repeat once on a different hero; if you do, may repeat once on a minion."

**Implementation (Long Shot):**
- `AttackSequenceStep` with `target_filters=[RangeFilter(min_range=stats.range, max_range=stats.range)]`. This reuses the exact min==max pattern Misa already uses (`scripts/misa_effects.py:414`).

**Implementation (Rain of Arrows):**
1. First attack at max range, `target_id_key="victim_1"` with `UnitTypeFilter` not required (any unit).
2. After combat, `CheckUnitTypeStep(unit_key="victim_1", expected_type="HERO", output_key="first_was_hero")`.
3. `MayRepeatOnceStep(active_if_key="first_was_hero", is_mandatory=True, ...)` — note: the rules say "repeat once on a different hero" is mandatory if able, so use `is_mandatory=True` on the inner select rather than on the repeat wrapper. The wrapper still exists only so the second shot is skipped entirely when the first target was not a hero.
4. Inner template:
   - `SelectStep(UNIT, filters=[UnitTypeFilter(HERO), TeamFilter(ENEMY), RangeFilter(min_range=stats.range, max_range=stats.range), ExcludeIdentityFilter(exclude_keys=["victim_1"])], output_key="victim_2")`.
   - `AttackSequenceStep(target_id_key="victim_2", range_val=stats.range)`.
   - `SetContextFlagStep(key="second_resolved", value=True)`.
5. Outer: second `MayRepeatOnceStep(active_if_key="second_resolved", is_mandatory=False)` template:
   - `SelectStep(UNIT, filters=[UnitTypeFilter(MINION), ..., ExcludeIdentityFilter(exclude_keys=["victim_1","victim_2"])], output_key="victim_3")`.
   - `AttackSequenceStep(target_id_key="victim_3", ...)`.

**Note on chained gating:** this is the canonical "A → (mandatory B) → (optional C)" chain. No new infra — the `active_if_key` + `ExcludeIdentityFilter` combo covers it, exactly like Arien's Violent Torrent with an added second tier of chaining.

**Difficulty: EASY–MEDIUM** — pattern is well-trodden; Rain of Arrows needs careful ordering of the two repeat wrappers.

**Existing pieces:** `AttackSequenceStep`, `RangeFilter(min==max)`, `MayRepeatOnceStep`, `CheckUnitTypeStep`, `ExcludeIdentityFilter`, `SetContextFlagStep`.
**New pieces:** None.
**Engine changes:** None.

---

### Family 3: Root Zones — BLUE (Grappling Branches / Entangling Vines / Grasping Roots)

**Effect text:** "This turn: Enemy heroes in radius cannot fast travel, or move more than 1 space with a movement action."

**Implementation:** Exact clone of Arien's `DelugeEffect` (`scripts/arien_effects.py:561`). One `CreateEffectStep(EffectType.MOVEMENT_ZONE, Shape.RADIUS, range=stats.radius, affects=ENEMY_HEROES, max_value=1, limit_actions_only=True, restrictions=[ActionType.FAST_TRAVEL])`.

**Difficulty: TRIVIAL** — copy-paste.

**New pieces:** None. **Engine changes:** None.

---

### Family 4: End-of-Turn Sentinel — BLUE (Treetop Sentinel / Warning Shot)

**Treetop Sentinel (III):** "End of turn: An enemy hero in radius discards a card, or is defeated."
**Warning Shot (II):** "End of turn: An enemy hero in radius discards a card, if able."

**Implementation:** Reuse the `DELAYED_TRIGGER` pattern from Min's grenade (`scripts/min_effects.py:666`). Key difference: scope is a hero-centered radius at resolve time, not a token hex. At *placement* time we snapshot Silverarrow's current hex into `finishing_steps` via an `origin_hex` on the inner filter, OR simpler: keep origin as `hero.id` and evaluate the radius when the delayed trigger fires.

Steps pushed into `finishing_steps`:
1. `SelectStep(UNIT, prompt="End of turn — select an enemy hero in radius", filters=[UnitTypeFilter(HERO), TeamFilter(ENEMY), RangeFilter(max_range=stats.radius, origin_id=hero.id)], is_mandatory=False, output_key="sentinel_victim")`.
2. `ForceDiscardOrDefeatStep(victim_key="sentinel_victim")` for Treetop; `ForceDiscardStep(victim_key="sentinel_victim")` for Warning.

**Open question:** Silverarrow may move between play and end-of-turn — we want the radius measured from her *end-of-turn* position, which is what `origin_id=hero.id` gives us automatically. Confirm `RangeFilter.origin_id` is resolved at filter-apply time (it is, per current implementation).

**Difficulty: EASY** — direct reuse of grenade pattern.

**New pieces:** None. **Engine changes:** None.

---

### Family 5: Drag-and-Dance — GREEN (Lead Astray / Divert Attention / Disorient)

**Effect text (Lead Astray III):** "Move an enemy unit adjacent to you up to 3 spaces; if you do, move up to that number of spaces in a straight line."
**Divert Attention (II):** up to 2.
**Disorient (I):** exactly 1 space + may move 1.

**Implementation (Lead Astray / Divert Attention):**
1. `SelectStep(UNIT, filters=[TeamFilter(ENEMY), RangeFilter(max_range=1)], is_mandatory=False, output_key="drag_target")`.
2. `SelectStep(NUMBER, number_options=[1..N], number_labels={1:"1 space", ...}, is_mandatory=False, active_if_key="drag_target", output_key="drag_distance")`. A `0`/SKIP option is available via `is_mandatory=False`.
3. `SelectStep(HEX, filters=[RangeFilter(max_range=stats_via_key, origin_key="drag_target"), ObstacleFilter(False), OccupiedFilter(False)], active_if_key="drag_distance", output_key="drag_dest")`. Uses existing `RangeFilter` but we need the max_range to come from context — today `RangeFilter.max_range` is a static int. **Landed** as `RangeFilter.max_range_key` (see PR1).
   - **Simplification:** skip the numeric prompt. Offer the player a single hex pick with `RangeFilter(max_range=N)` around the drag target, then derive distance from prior/new hex. This is cleaner.
4. **Snapshot + post-move distance.** `RecordHexStep(unit_key="drag_target", output_key="drag_start_hex")` *before* the nudge, then `MoveUnitStep(unit_key="drag_target", destination_key="drag_dest", is_movement_action=False)`, then `ComputeDistanceStep(unit_key="drag_target", hex_key="drag_start_hex", output_key="drag_distance_moved")`. No `MoveUnitStep` extension needed — `RecordHexStep` already existed and `ComputeDistanceStep` is a new standalone step added in PR1 (reusable for any "distance moved since X" logic).
5. Self-move, in a straight line, up to `drag_distance_moved` spaces. **This is an effect-side nudge, not a MOVEMENT action**, so use `SelectStep + MoveUnitStep`, NOT `MoveSequenceStep`:
   - `SelectStep(TargetType.HEX, output_key="self_dest", is_mandatory=False, active_if_key="drag_distance_moved", filters=[RangeFilter(max_range=0, max_range_key="drag_distance_moved", origin_id=hero.id), InStraightLineFilter(origin_id=hero.id), StraightLinePathFilter(origin_id=hero.id), ObstacleFilter(False), OccupiedFilter(False)])`.
   - `MoveUnitStep(unit_id=hero.id, destination_key="self_dest", is_movement_action=False, active_if_key="self_dest")`.

**Disorient (I)** is a fixed 1/1 variant and collapses to the existing "nudge enemy 1 space + optional self-move-1" pattern already in Arien's card (`arien_effects.py:103`), which itself uses `SelectStep + MoveUnitStep` — confirm and clone.

**Difficulty: MEDIUM** — the logic is simple. Requires one new step and one filter-field addition:
- `ComputeDistanceStep(unit_key|unit_id, hex_key|other_unit_key, output_key)` — new standalone step that stores a topology-aware integer distance in context. Reusable beyond Silverarrow.
- `RangeFilter.max_range_key` (read upper bound from context) — mirrors existing `origin_key`.

**Existing pieces:** `SelectStep`, `RecordHexStep`, `MoveUnitStep`, `RangeFilter`, `InStraightLineFilter`, `StraightLinePathFilter`, `ObstacleFilter`, `OccupiedFilter`.
**New pieces:** `ComputeDistanceStep` (step).
**Engine changes:** New step + one field addition on `RangeFilter`. `MoveUnitStep` is untouched. No `MoveSequenceStep` — these self-moves are effect-side nudges, not MOVEMENT actions.

---

### Family 6: Gift Retrieve — GREEN (Nature's Blessing / Fae Healing)

**Nature's Blessing (III):** "A hero in radius may retrieve a discarded card; if they do, that hero gains 2 coins."
**Fae Healing (II):** same, 1 coin.

**Implementation:**
1. `SelectStep(UNIT, prompt="Gift a card retrieval", filters=[UnitTypeFilter(HERO), TeamFilter(FRIENDLY), RangeFilter(max_range=stats.radius)], skip_immunity_filter=True, is_mandatory=False, output_key="gift_hero")`.
2. `SelectStep(CARD, card_container=DISCARD, context_hero_id_key="gift_hero", override_player_id_key="gift_hero", is_mandatory=False, active_if_key="gift_hero", output_key="gift_card")`.
3. `RetrieveCardStep(card_key="gift_card", hero_key="gift_hero", active_if_key="gift_card")` — `hero_key` already exists on `RetrieveCardStep` (`steps.py:6039`), no extension needed.
4. `GainCoinsStep(hero_key="gift_hero", amount=2, active_if_key="gift_card")` — already exists and already takes `hero_key`.

**Difficulty: TRIVIAL** — pure reuse.

**Existing pieces:** `SelectStep`, `GainCoinsStep`, `RetrieveCardStep` (with `hero_key`), `override_player_id_key` (opponent-style delegation, used here for teammates).
**New pieces:** None.
**Engine changes:** None.

---

### Family 7: Max-Range + Escape — GOLD (Shoot and Scoot, untiered)

**Effect text:** "Target a unit at maximum range. After the attack: If able, you may fast travel to an adjacent zone."

**Implementation:**
1. `AttackSequenceStep(damage=stats.primary_value, range_val=stats.range, target_filters=[RangeFilter(min_range=stats.range, max_range=stats.range)])`.
2. `FastTravelSequenceStep(unit_id=hero.id)` — already optional (`is_mandatory=False` is built into the macro's inner select). "Adjacent zone" is naturally enforced by the existing `FastTravelDestinationFilter` + `get_safe_zones_for_fast_travel`.

**Difficulty: TRIVIAL**. **New pieces / engine changes:** None.

---

### Family 8: Friendly Ignore-Obstacles Zone — SILVER (Trailblazer, untiered)

**Effect text:** "You may fast travel, if able. This round: You and friendly heroes in radius may ignore obstacles while performing movement actions."

**Implementation:**
1. `FastTravelSequenceStep(unit_id=hero.id, is_mandatory=False)`.
2. `CreateEffectStep` of a **new** `EffectType.MOVEMENT_AURA_ZONE` with:
   - `scope=EffectScope(shape=Shape.RADIUS, range=stats.radius, origin_id=hero.id, affects=AffectsFilter.SELF_AND_FRIENDLY_HEROES)`
   - `duration=DurationType.THIS_ROUND`
   - a new flag `grants_pass_through_obstacles: bool = True` on `ActiveEffect`.

   **Note:** `AffectsFilter.FRIENDLY_HEROES` excludes self (see `validation.py:762`), so using it would make Silverarrow the only hero *not* benefiting from her own aura. A new `AffectsFilter.SELF_AND_FRIENDLY_HEROES` value was added in PR1 to carry the "you + friendlies" semantics cleanly at the filter layer, rather than special-casing self inside `MoveSequenceStep`.
3. **Rules integration: the check lives inside `MoveSequenceStep`**, because `MoveSequenceStep` is the unique entry point for MOVEMENT actions, and the text says "while performing movement actions". At the top of `MoveSequenceStep.resolve()` (before it dispatches into `MoveUnitStep`), consult `get_movement_aura_for(state, unit_id)` which merges:
   - the mover's own card-passive `MovementAura` (existing, via `get_movement_aura()`), and
   - any active `MOVEMENT_AURA_ZONE` effects whose scope covers the mover's *current* hex and whose `affects` matches the mover.
   The merged `MovementAura` is then passed down as `pass_through_obstacles=True` into the pathfinding call — effect-side `MoveUnitStep` calls (Family 5, Wild Hunt, etc.) do NOT pass through this path and therefore do not pick up the zone aura, which is the correct behavior per the card text.

**Subtlety:** the radius is measured at move-*start*, not at each pathfinding step — matching how other auras behave. We do **not** rebuild pathfinding for mid-move radius checks.

**Difficulty: MEDIUM** — one new `EffectType`, one `ActiveEffect` flag, one helper, and one integration point inside `MoveSequenceStep`. Pattern mirrors existing `MOVEMENT_ZONE` but grants rather than restricts, and attaches to the movement-action entry point instead of generic pathfinding.

**Existing pieces:** `CreateEffectStep`, `FastTravelSequenceStep`, `MovementAura` plumbing.
**New pieces:**
- `EffectType.MOVEMENT_AURA_ZONE` enum value.
- `AffectsFilter.SELF_AND_FRIENDLY_HEROES` enum value (for the "you + friendlies" scope).
- `ActiveEffect.grants_pass_through_obstacles` field.
- Call site: `MoveSequenceStep.resolve()` — iterates `state.active_effects` for `MOVEMENT_AURA_ZONE` entries in scope and ORs their grant with the mover's card-passive `MovementAura`. No separate `rules.get_movement_aura_for` helper needed; the merge lives inline in `MoveSequenceStep` next to the existing card-aura lookup.

---

### Family 9: Ultimate — Wild Hunt (PURPLE, passive)

**Effect text:** "Each time before you perform an action, you may move 2 spaces in a straight line."

**Implementation:**
- `PassiveConfig(trigger=PassiveTrigger.BEFORE_ACTION, uses_per_turn=0, is_optional=True, prompt="Wild Hunt: move 2 in a straight line?")`.
- `get_passive_steps` returns an **effect-side nudge**, not a MOVEMENT action — so `SelectStep + MoveUnitStep`, NOT `MoveSequenceStep`:
  ```
  SelectStep(
      target_type=TargetType.HEX,
      output_key="wild_hunt_dest",
      is_mandatory=False,
      filters=[
          RangeFilter(max_range=2, origin_id=hero.id),
          InStraightLineFilter(origin_id=hero.id),
          StraightLinePathFilter(origin_id=hero.id),
          ObstacleFilter(is_obstacle=False),
          OccupiedFilter(is_occupied=False),
      ],
  )
  MoveUnitStep(
      unit_id=hero.id,
      destination_key="wild_hunt_dest",
      is_movement_action=False,
      active_if_key="wild_hunt_dest",
  )
  ```
  Hardcoded distance 2 — the text is not buffable. Because this is not a MOVEMENT action, Wild Hunt does **not** consult Trailblazer's ignore-obstacles zone (correct per the card texts: Trailblazer explicitly scopes its aura to movement actions).

**New pieces: `PassiveTrigger.BEFORE_ACTION`**
- Enum value in `domain/models/enums.py`.
- Fan-out in `ResolveCardStep` (or wherever `BEFORE_ATTACK` / `BEFORE_MOVEMENT` / `BEFORE_SKILL` are currently dispatched): emit `BEFORE_ACTION` *in addition* to the specific trigger so Wild Hunt catches all three, and any future "before any action" passives work uniformly.
- Alternative: leave `BEFORE_ACTION` out and instead implement Wild Hunt as three separate `PassiveConfig` entries (one per existing trigger). This is cheaper (no engine change) but costs correctness: `uses_per_turn=0` means "unlimited", which matches Wild Hunt's wording — three configs would each count independently, which is fine. **However**, having one canonical `BEFORE_ACTION` trigger is cleaner and future-proofs other "before every action" cards.

**Recommended:** add the new trigger. It's a 10-line change in `domain/models/enums.py` + the dispatcher.

**Also beware:** `BEFORE_ACTION` must fire *before* the action's own pre-action movement window (so the 2-space move happens before, say, Misa's Focus pre-action move). Verify ordering in the dispatcher — this is exactly the interaction the existing ordering bug fix touched (`cfd986d: petrifying stare no longer blocks non-action movement`), so there's prior art for the pre-action move window.

**Difficulty: MEDIUM** — new passive trigger plus careful dispatcher ordering.

---

## Summary: Novel vs Reused

| Family | Novelty | New Infra |
|---|---|---|
| 1. Isolated snipe (Red) | Trivial | `CountMatchFilter` accepts unit candidates ✅ PR1 |
| 2. Max-range snipe (Red) | None | — |
| 3. Root zones (Blue) | None (Deluge clone) | — |
| 4. End-of-turn sentinel (Blue) | None (grenade clone) | — |
| 5. Drag-and-dance (Green) | Low | `ComputeDistanceStep` (new step), `RangeFilter.max_range_key` ✅ PR1 |
| 6. Gift retrieve (Green) | None | — (`RetrieveCardStep.hero_key` already existed) |
| 7. Shoot and Scoot (Gold) | None | — |
| 8. Trailblazer (Silver) | **Medium** | `EffectType.MOVEMENT_AURA_ZONE` + `AffectsFilter.SELF_AND_FRIENDLY_HEROES` + `grants_pass_through_obstacles` + `MoveSequenceStep` hook ✅ PR1 |
| 9. Wild Hunt (Ultimate) | **Medium** | `PassiveTrigger.BEFORE_ACTION` + dispatcher fan-out (fires on any choice incl. HOLD) ✅ PR1 |

**PR1 status: landed.** All engine prereqs below are on `main` with 1330 passing tests.

**Engine-level work:**
1. `MOVEMENT_AURA_ZONE` effect type + `AffectsFilter.SELF_AND_FRIENDLY_HEROES` + `MoveSequenceStep` integration — the biggest piece.
2. `BEFORE_ACTION` passive trigger + dispatcher fan-out (primary + secondary + HOLD) — small but engine-level.
3. `CountMatchFilter.apply()` generalized to accept unit-ID candidates — ~10 lines.
4. `ComputeDistanceStep` — new standalone step for post-move distance tracking.
5. `RangeFilter.max_range_key` / `min_range_key` — context-driven bounds.

Everything else is pure composition of existing building blocks.

---

## Suggested Build Order

1. **Engine prerequisites (PR 1) ✅ DONE:** `CountMatchFilter` unit-ID generalization, `ComputeDistanceStep`, `RangeFilter.max_range_key`, `EffectType.MOVEMENT_AURA_ZONE` + `AffectsFilter.SELF_AND_FRIENDLY_HEROES` + `MoveSequenceStep` integration, `PassiveTrigger.BEFORE_ACTION` with dispatcher fan-out (fires on primary/secondary/HOLD). Covered by `tests/engine/test_silverarrow_prereqs.py` (12 tests).
2. **Trivial families (PR 2):** Families 2, 3, 4, 7 — all reuse existing patterns.
3. **Family 1 + 5 + 6 (PR 3):** Once engine prereqs are in.
4. **Family 8 + 9 (PR 4):** Trailblazer zone and Wild Hunt ultimate — the two pieces that exercise the new engine infra end-to-end.
5. **Integration tests (PR 5):** Full-hero test suite in `tests/engine/test_silverarrow_*.py`, one file per family.
