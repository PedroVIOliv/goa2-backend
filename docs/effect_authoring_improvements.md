# Effect Authoring & Engine Improvement Backlog

Captured 2026-06-10 after implementing the full Trinkets card set (17 deck cards + ultimate).
These are observations grounded in friction hit while writing real effects — not speculative
refactors. Each item notes the symptom, the evidence, the proposed fix, and rough effort/risk
so we can pick them up independently later.

**Guiding principle:** the core architecture (logic-as-data, LIFO step stack, resumable input)
is sound and should not change. Every item below is *additive* — old effects keep working
untouched. The weaknesses are in the **authoring layer** on top of the stack, and in a few
**infrastructure** spots where mirrored logic has drifted.

Priority legend: 🔴 high value / low cost · 🟡 high value / moderate cost · 🟢 nice-to-have

---

## Infrastructure

### 🔴 I1. Consolidate the two `affects`-filter dispatchers
**Symptom:** `stats.py:_matches_affects_filter` and `validation_effects.py`'s affects-matching
are near-duplicates and have drifted **twice in a single day**:
- `SELF_AND_FRIENDLY_HEROES` case was missing entirely from `stats.py` (auras silently applied
  to nobody).
- `FRIENDLY_HEROES` excluded self in validation but *included* self in stats.

Both bugs were invisible until a card (Trinkets barriers) actually exercised the path.

**Fix:** extract one shared `matches_affects(effect, target_id, state) -> bool` helper and call
it from both sites. Same argument applies to the duplicated candidate-gathering logic in
`SelectStep._get_candidates`, `MultiSelectStep`, and `CountStep`.

**Effort:** small. **Risk:** low (covered by existing 1548 tests + the two new self-exclusion tests).

---

### 🔴 I2. Auto-patch polymorphic step/filter fields in `step_types.py`
**Symptom:** the `AnyStep`/`AnyFilter` unions are already auto-built from subclasses (good), but
any step with a `list[FilterCondition]` or `list[GameStep]` field *still* needs a manual entry in
`rebuild_serialization_models()`. CLAUDE.md itself calls this "the most common cause of
persistence failures." Adding `CheckUnitFiltersStep` today required remembering to patch its
`filters` field by hand.

**Fix:** the condition is mechanically detectable — iterate registered step/filter classes, find
fields whose annotation resolves to `GameStep`/`FilterCondition` (or lists thereof), and patch +
rebuild them in a loop. Eliminates the checklist item and the whole failure class.

**Effort:** small–medium. **Risk:** low–medium (touches serialization; round-trip tests guard it).

---

### 🟡 I3. Make `is_active` semantics uniform on effects
**Symptom:** `_is_effect_active` only consults the `is_active` flag when the effect has a
`source_card_id`; non-card-bound effects ignore it. This means `deactivate_effect_by_id` is a
silent no-op for any effect that isn't card-bound. The Trinkets disruptor only deactivates
correctly because it happens to be card-bound. A future "deactivate on trigger" effect that isn't
card-bound would fail quietly.

**Fix:** always respect `is_active`, and ensure it's set correctly at creation time for every
effect. Audit existing effects for reliance on the current lenient behavior.

**Effort:** medium. **Risk:** medium (changes activation gating; needs careful test coverage).

---

### 🟡 I4. General "actor left the board mid-action" guard
**Symptom:** `ResolveCardStep` checks the actor is on-board, but `ResolveCardTextStep` and the
rest of the action chain do not. Trinkets' Disruptor Grid can defeat the acting hero *before*
their primary action resolves, so `ResolvePreActionDiscardStep` had to handle the
"actor gone → abort" case locally. Every future "defeat before/during action" effect will have to
re-solve this.

**Fix:** a defeated-actor check in the handler loop (or at minimum in `ResolveCardTextStep`) that
aborts the remaining action chain when the current actor is no longer on the board.

**Effort:** small–medium. **Risk:** medium (central loop; verify no double-abort with existing
abort cascade).

---

### 🟢 I5. Smaller paper cuts
- **`DurationType` lives in `domain/models/effect.py`**, not `enums.py` like every other enum.
  Easy to import-guess wrong (I did); the card-effects skill template implies the wrong location.
  Re-export from `enums.py` or move it.
- **`ObstacleFilter` has `type = FilterType.OCCUPIED`** and conflates "obstacle" with "occupied"
  via `is_obstacle_for_actor`. Naming actively misleads. No clean way to express "hex is empty"
  vs "hex is not terrain" distinctly.
- **`PlaceTokenStep` silently no-ops on an occupied hex**, so every placement effect must remember
  the right hex filters or the player's selection just vanishes. Fail loudly, or route placement
  through a shared select-helper that always applies the obstacle/occupancy filter.
- **Test builders should grow `.with_token_pool(TokenType.X)`** — Mortimer (`_add_zombie_pool`)
  and now Trinkets (`_add_barrier_pool`) each hand-roll the same helper.

---

## Authoring Ergonomics

The foundation is right — 17 effects needed only 2 new steps, and "pause mid-action for the
*victim* to choose a discard" falls out for free. But the layer authors actually write against
has sharp edges.

### 🟡 A1. First-class branching (`ChooseOneStep` / `IfStep`)
**Symptom:** "Choose one —" is the worst thing to write. The current idiom is:
NUMBER select → `CheckContextConditionStep` per branch → `active_if_key` manually threaded onto
*every step of every branch*. `rapid_redeployment` spends ~90 flat lines on two branches with the
branch structure invisible; Salvage Parts and Perfected Design pay the same tax.

The stack already has control-flow composites (`ForEachStep`, `MayRepeatNTimesStep`) — branching
just never got one.

**Fix:**
```python
ChooseOneStep(options=[
    ("Move and redeploy", [ ...steps... ]),
    ("Defeat adjacent minion", [ ...steps... ]),
])
IfStep(condition_key="...", then_steps=[...], else_steps=[...])
```
Collapses all three of today's choice cards to ~⅓ the code and removes the key-threading entirely.

**Effort:** medium. **Risk:** low (new composite steps; additive). **Payoff:** 3 existing cards
simplify immediately; every future choice card benefits.

---

### 🔴 A2. Context-key lint (producer/consumer checking)
**Symptom:** context keys are stringly-typed with no checking. A typo in
`active_if_key="salvage_remove_retreive"` raises nothing — the step just skips forever and the
card silently half-works. Same for `target_key`, `destination_key`, etc. This is the scariest
property of the current model: failures are silent and surface only in playtest.

**Fix:** a test that iterates every registered effect, calls `build_steps()` against a stub
state, walks the returned step list, and asserts every *consumed* key (`active_if_key`,
`skip_if_key`, `*_key` fields) has an upstream *producer* (`output_key`, or a known composite
default like `victim_id`). Catches the whole class at CI time.

Caveats to handle: composite steps that produce keys internally (e.g. `AttackSequenceStep` →
`victim_id`), and templated steps (`ForEachStep`/repeat templates) whose producers live in the
template. Start strict-with-allowlist; loosen as needed.

**Effort:** small–medium. **Risk:** low (test-only; no runtime change). **Pays off immediately.**

---

### 🟡 A3. Scoped context frames for templated steps
**Symptom:** context is one flat shared namespace. Composite steps hardcode keys
(`AttackSequenceStep` → `victim_id`, `ForceDiscardStep` → `card_to_discard`), which is fine until
two interleave — two pending discards would stomp each other's selection key. We avoided
collisions today *only* by manually prefixing everything (`salvage_*`, `redeploy_*`, `cannon_*`).
That convention lives entirely in authors' heads.

**Fix (short term):** document the prefixing convention in `EFFECT_AUTHOR_REFERENCE.md` as a hard
rule.
**Fix (longer term):** have templated steps (`ForEachStep`, repeat templates) push/pop a scoped
context frame instead of sharing the global dict, so iteration N can't see iteration N-1's keys.

**Effort:** doc=tiny, scoping=medium. **Risk:** scoping touches the shared context contract — do
it carefully behind tests.

---

### 🟢 A4. Stop proliferating special-case check steps
**Symptom:** ~85 `StepType`s now, several special cases of each other.
`CheckAdjacencyStep`, `CheckDistanceStep`, `CheckUnitTypeStep` are all expressible as the new
`CheckUnitFiltersStep` with the right filters. `CountStep` + `CheckContextConditionStep` is a
two-step idiom that's really one operation ("is there an adjacent enemy?"). Every extra step is
union registration + guardrail-list maintenance + one more thing authors must know exists.

**Fix:** promote `CheckUnitFiltersStep` (filter-based) as the canonical single-unit check; fold
count+threshold into `CountStep` (add an optional `operator`/`threshold` + `output_key` that
stores the boolean). Don't add bespoke check steps going forward. Leave existing ones in place
(deprecate in docs, don't break saves).

**Effort:** small per fold. **Risk:** low (additive; old steps stay for persistence).

---

### 🟢 A5. Shared cross-hero recipe module
**Symptom:** three lines of card text → ~60 lines of steps. The family-base-class pattern
(`_DualOriginCannonEffect`, `_TurretAdjacentAttackEffect`, etc.) keeps tier variants nearly free
and is the right per-hero mitigation. But recurring *cross-hero* patterns are re-derived: "attack
with extra target filters + repeat on different units" now exists in Xargatha (`rapid_thrusts`),
Widget, and Trinkets in slightly different shapes.

**Fix:** promote stable cross-hero patterns into a shared `scripts/recipes.py` (or similar) of
step-list builders. Only promote once a pattern appears in 2–3 heroes — premature extraction is
worse than duplication.

**Effort:** ongoing/incremental. **Risk:** low.

---

## Suggested order of attack

If picking these up later, rough ROI order:

1. **A2 (context-key lint)** — cheap, test-only, catches a silent failure class immediately.
2. **I2 (auto-patch unions)** — mechanical, kills the documented #1 persistence footgun.
3. **I1 (consolidate affects dispatchers)** — small, prevents a bug that already recurred twice.
4. **A1 (`ChooseOneStep`)** — biggest authoring ergonomic win; 3 cards simplify on day one.
5. Then I3/I4/A3 as appetite allows; I5/A4/A5 are opportunistic cleanup.

All of 1–4 are additive and verifiable against the existing suite.
