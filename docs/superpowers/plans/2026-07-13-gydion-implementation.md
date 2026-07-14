# Gydion First-Six-Spells Implementation Plan

> **Status: READY FOR IMPLEMENTATION (2026-07-13).** Rules are approved; no
> production implementation has started.

**Goal:** Implement Gydion's unique hidden spellbook, normal-action casting
pipeline, the six approved spells, every access card that can reach them, and
the required client/persistence contracts using test-driven development.

**Authoritative specification:**
`docs/superpowers/plans/2026-07-13-gydion-tdd-paths.md`. Its locked
interpretations, S1-S11 decisions, and H/U paths are binding. This document
only defines the safe implementation order and concrete file ownership.

**Architecture:** `SpellCard` inherits `Card`, so normal Hold/Clear/Fast
Travel generation and stat computation remain shared. Gydion holds a master
spell list whose state divides it into hidden spellbook and public outside
zones. `CastSpellStep` handles allowed-card selection and immediate faceup
spending, then delegates the chosen spell to a generalized performed-card
action dispatcher. A stacked performing-card/action context makes the nested
spell action a complete action without confusing it with the outer played
card. Effects remain ordinary registered `CardEffect` step factories.

**Tech stack:** Python 3.11+, Pydantic V2, pytest. Baseline at planning time:
`2751 passed`.

## Global constraints

- Read the TDD-path document and the files named in a task before editing.
- Use `build_steps()`, not `get_steps()`, for every effect.
- Effect flows use `EffectScenarioBuilder` + `run_card`; primitive tests use
  `push_steps` + `process_stack`.
- Every new concrete step/filter gets a unique `StepType`/`FilterType`; the
  serialization unions auto-discover them.
- Player input uses `InputRequest`; observable state changes emit
  `GameEvent`s.
- Spell identities inside the spellbook are secret. Do not place full
  spellbook objects in a non-owner view, generic event, or spectator payload.
- A spell is a source card during its action, but never a planned, committed,
  discarded, retrieved, upgraded, or item card.
- Avoid a third copy of the card-action menu. Extend/extract the existing
  performed-card pipeline and keep ordinary `ResolveCardStep` behavior stable.
- New client fields/events are additive contract changes: update
  `docs/CLIENT_INTEGRATION_GUIDE.md` and add server/player-scope tests.
- Run the focused test first, then the full suite after every task. Final code
  must also pass ruff, black check, and mypy.

## File structure

| File | Responsibility |
|---|---|
| `src/goa2/domain/models/spell.py` | `SpellCard(Card)` and spell metadata |
| `src/goa2/domain/models/enums.py` | spell card states and new step types |
| `src/goa2/domain/models/__init__.py` | export `SpellCard` |
| `src/goa2/domain/models/unit.py` | `Hero.spells` master list and computed zone helpers |
| `src/goa2/domain/state.py` | unique spellbook-owner and source-card lookup |
| `src/goa2/data/heroes/gydion.py` | six spell definitions and access-card data correction |
| `src/goa2/engine/steps/cards.py` | generalized performed-card action lifecycle |
| `src/goa2/engine/steps/phases.py` | nested action-context restoration if kept with current restore step |
| `src/goa2/engine/steps/spells.py` | cast/prepare primitives |
| `src/goa2/engine/steps/__init__.py` | export spell steps |
| `src/goa2/engine/stats.py` | stat auras use performing source card |
| `src/goa2/engine/steps/combat.py` | basic classification uses performing source card |
| `src/goa2/domain/events.py` | spell cast/prepared events |
| `src/goa2/domain/views.py` | owner-private spellbook and public outside spells |
| `src/goa2/domain/models/effect.py` | `basic_attacks_only` immunity payload |
| `src/goa2/engine/steps/effects.py` | create/pass through immunity payload |
| `src/goa2/engine/filters_units.py` | basic-only immunity evaluation |
| `src/goa2/scripts/gydion_effects.py` | access effects and six spell effects |
| `tests/engine/effects/gydion_common.py` | fresh cards/spells and scenario helpers |
| `tests/domain/test_spell_card.py` | SpellCard/state/domain contracts |
| `tests/engine/test_spell_action_context.py` | generalized nested action primitive |
| `tests/engine/test_spellbook_steps.py` | cast/prepare/events/persistence |
| `tests/domain/test_spellbook_views.py` | owner/opponent/spectator visibility |
| `tests/engine/test_basic_only_attack_immunity.py` | Shield engine primitive |
| `tests/engine/effects/cases/test_gydion_access.py` | Prepare/access/partial-scope flows |
| `tests/engine/effects/cases/test_gydion_cantrips.py` | three basic spells |
| `tests/engine/effects/cases/test_gydion_elementary.py` | Burning Hands/Suggestion/Shield |
| `tests/server/test_spellbook_contract.py` | REST/WS scoped contract and save/load |
| `docs/CLIENT_INTEGRATION_GUIDE.md` | new fields, states, and events |

## Dependency order

```text
T1 Spell model/data/state lookup
 ├─> T2 nested card-action source/lifecycle
 ├─> T3 cast/prepare/events/views/persistence
 └─> T4 basic-only attack immunity

T2 + T3 ─> T5 access cards + Prepare effect
T2 + T3 + T5 ─> T6 cantrip spell effects
T2 + T3 + T4 + T5 ─> T7 elementary spell effects
T5 + T6 + T7 ─> T8 copied/repeat/full-round regressions + final gates
```

T2-T4 touch mostly disjoint files and are conceptually independent after T1,
but a single-session implementation should run them sequentially to keep the
full-suite signal simple. T5-T7 all edit `gydion_effects.py`; run those
sequentially.

---

### Task 1: SpellCard model, Gydion spell data, states, and lookup (P1; TDD §1)

**Files:** create `domain/models/spell.py`; modify `enums.py`, model exports,
`unit.py`, `state.py`, and `data/heroes/gydion.py`; create
`tests/domain/test_spell_card.py` and `tests/engine/effects/gydion_common.py`.

**Interfaces produced:**

- `SpellCard(Card)` with spell-rank metadata and inherited action validators.
- `CardState.SPELLBOOK` / `CardState.OUTSIDE_SPELLBOOK`.
- `Hero.spells: list[SpellCard] = []`, plus read-only prepared/outside helpers.
- `GameState.get_spellbook_owner()` and card lookup that includes spells.
- Six exact spell definitions from the approved table.

**Implementation notes:**

- Basic spells use GOLD + UNTIERED so `Card.is_basic` stays authoritative;
  colored spells use their Tier-I colors. Set inert `initiative=0`, no item.
- Initialize all six outside/faceup. `Hero.initialize_state()` must never move
  them into the normal hand.
- Keep one object per spell in the master list; never copy it between lists.
- Correct the existing `lesser_enchantment.item` constructor to
  `StatType.DEFENSE` while touching Gydion data.

- [ ] Write every §1 H/U test, including exact generated menus and JSON subtype
  round-trip.
- [ ] Run focused tests and confirm they fail before the model exists.
- [ ] Implement the smallest model/data/state surface.
- [ ] Run focused tests, then `PYTHONPATH=src uv run pytest tests/ -q`.
- [ ] Suggested commit: `feat: add Gydion spell card model and six spell data`

---

### Task 2: Nested performing-card action lifecycle (P2; TDD §3-§4 backbone)

**Files:** modify `engine/steps/cards.py`, `engine/steps/phases.py` as needed,
`engine/stats.py`, `engine/steps/combat.py`, `domain/state.py`, and enums/step
exports if a restore step is added; create
`tests/engine/test_spell_action_context.py`.

**Interfaces produced:**

- A performing-card lookup that prefers the nested action source over
  `current_turn_card` and includes spell cards.
- A stacked action context containing at least `current_action_type`,
  `current_card_id`, and `performing_card_id`, restored on all exit paths.
- `PerformCardActionStep` support for finding a spell on the owner and running
  a full action lifecycle while suppressing only inner `AFTER_RESOLVE_CARD`.
- Repeat machinery can find/reperform a spell action without casting it again.

**Required hook order:** mirror `ResolveCardStep`: BEFORE_ACTION, specific
BEFORE trigger, primary text or secondary primitive, specific AFTER trigger,
basic hooks when applicable, AFTER_PRIMARY_ACTION when primary, then restore.
The outer step remains responsible for its own later hooks and
`AFTER_RESOLVE_CARD`.

**Regression protections:**

- Keep current Mind Grip options, token substitution, marker skipping, actor
  routing, and stats unchanged.
- Existing attacks still derive basic/ranged state from their ordinary source
  card.
- Basic-only stat auras consult the performing spell during the nested action
  and the outer card immediately after restoration.

- [ ] Write §4 H1-H4/H7-H8 and U1-U3 as failing raw-stack/contract tests.
- [ ] Add explicit non-spell `ResolveCardStep` and Mind Grip regressions.
- [ ] Implement context push/restore and generalize the dispatcher.
- [ ] Verify a serialized stack resumes at both spell-action input boundaries.
- [ ] Run focused and full suites.
- [ ] Suggested commit: `feat: support nested full card actions with source context`

---

### Task 3: Cast/prepare steps, events, views, and persistence (P3-P4; TDD §2-§3)

**Files:** create `engine/steps/spells.py`; modify step exports/enums,
`domain/events.py`, `domain/views.py`, `domain/state.py`, client guide; create
`tests/engine/test_spellbook_steps.py`, `tests/domain/test_spellbook_views.py`,
and `tests/server/test_spellbook_contract.py`.

**`CastSpellStep` contract:**

1. Resolve unique owner and caster.
2. Intersect `allowed_spell_ids` with prepared spells.
3. Zero → clean finish; one → auto-select; multiple → `SELECT_CARD` to caster.
4. Validate pending selection against the current option set.
5. Move selected spell outside/faceup and emit `SPELL_CAST`.
6. Write owner/caster/spell IDs and push Task-2 performed-card action flow.

**`PrepareSpellbookStep` contract:**

1. Find every outside spell.
2. Expire effects bound to each returning card before hiding it.
3. Set each to SPELLBOOK/facedown.
4. Emit one `SPELLBOOK_PREPARED` event containing only public return data.
5. Be idempotent on a full book.

**View contract:** `spellbook` full for owner/reveal-all, count-only otherwise;
`cast_spells` faceup/public; null/empty for heroes without spells. Document the
additive shape and events in the client guide.

- [ ] Write all §2 and §3 tests before implementation, including invalid stale
  input, immediate spend timing, owner/opponent/spectator views, REST/WS, and
  JSON save/load.
- [ ] Add unique step/event enum values and implement both steps.
- [ ] Update view builder and client guide together.
- [ ] Run engine/domain/server focused tests, then full suite.
- [ ] Suggested commit: `feat: add spellbook cast prepare and client contracts`

---

### Task 4: Basic-only attack immunity for Shield (P5; TDD §11 primitive paths)

**Files:** modify `domain/models/effect.py`, `engine/steps/effects.py`, and
`engine/filters_units.py`; create
`tests/engine/test_basic_only_attack_immunity.py`.

**Interface:** keep Shield on the existing
`CreateEffectStep(ATTACK_IMMUNITY, ...)` path used by Arien's Expert/Master
Duelist and Tigerclaw's Blend Into Shadows. Add
`ActiveEffect.basic_attacks_only: bool = False` and the same generic payload
on `CreateEffectStep`, pass it through the manager's existing effect-payload
path, and have `ImmunityFilter` ignore that immunity for a non-basic attack
while blocking a basic attack. Reuse `AttackSequenceStep`'s pre-selection
`attack_is_basic` context, whose semantics are already exercised by Snorri's
Oath effects. Do not add a Shield-specific step or a new immunity type.

- [ ] First test a protected hero against ordinary basic and non-basic attacks.
- [ ] Test basic and non-basic performed-card overrides.
- [ ] Assert existing `ATTACK_IMMUNITY` with the default still blocks all
  attacks and exception-attacker behavior remains intact.
- [ ] Implement payload plumbing and filter gate.
- [ ] Run focused and full suites.
- [ ] Suggested commit: `feat: support basic-only attack immunity`

---

### Task 5: Gydion access cards and Prepare Spells effect (TDD §5 plus §2 flow)

**Files:** create `scripts/gydion_effects.py`; create
`tests/engine/effects/cases/test_gydion_access.py`.

**Interfaces produced:**

- `PrepareSpellsEffect` → `PrepareSpellbookStep`.
- Shared `SpellAccessEffect` whose configured allowed IDs produce one
  `CastSpellStep` with the current performer as caster.
- Registrations for all 16 access effect IDs, using the complete printed map.
  The cast step naturally intersects it with the first-six implementation.

**Map required in this phase:**

- Cantrip → Shocking Grasp / Magic Missile / Expeditious Retreat.
- Evocation I/II/III → Burning Hands (+ absent higher spells ignored).
- Abjuration I/II/III → Shield (+ absent higher spells ignored).
- Enchantment I/II/III → Suggestion (+ absent higher spells ignored).
- Necromancy/Conjuration/Transmutation II/III → registered but empty today.
- The Archwizard/Wish stays inert.

- [ ] Write §5 H/U paths and full Prepare card flow first.
- [ ] Assert unavailable primary spell text does not remove secondary actions
  from the outer deck card.
- [ ] Implement registrations and shared access base.
- [ ] Run focused and full suites.
- [ ] Suggested commit: `feat: implement Gydion spell access cards`

---

### Task 6: Cantrip spells (TDD §6-§8)

**Files:** extend `scripts/gydion_effects.py`; create
`tests/engine/effects/cases/test_gydion_cantrips.py`.

**Shocking Grasp assembly:** `AttackSequenceStep` with a stable target key,
then optional target-origin hex selection and `MoveUnitStep`. Do not require
the attack target to be movable—the attack is still legal when the rider is
not.

**Magic Missile assembly:** ranged `AttackSequenceStep`, computed Range, plus
minimum-distance-2 targeting.

**Expeditious Retreat assembly:** primary `MoveSequenceStep` with
`force_straight_line=True`, full distance not forced.

- [ ] Write every §6-§8 path, including all secondary-action paths, block/
  defeat outcomes, stat items, range minimum, ranged defense, and straight
  movement.
- [ ] Implement the three registered spell effects using existing primitives.
- [ ] Run focused and full suites.
- [ ] Suggested commit: `feat: implement Gydion cantrip spells`

---

### Task 7: Burning Hands, Suggestion, and Shield (TDD §9-§11)

**Files:** extend `scripts/gydion_effects.py`; create
`tests/engine/effects/cases/test_gydion_elementary.py`.

**Burning Hands order:** mandatory adjacent attack-target selection → optional
enemy-hero selection at exact distance 1 from that target → victim-controlled
`ForceDiscardStep` → `AttackSequenceStep(target_id_key=...)`. Its reaction
window must open after the discard.

**Suggestion order:** mandatory enemy-hero selection in computed Radius using
only the normal hero/team/range/immunity filters → mandatory destination
selection at exact distance 3 using the existing range, straight-line,
straight-path, obstacle, and movement-path filters → forced
`MoveUnitStep(range_val=3, is_movement_action=False)`. Do not prefilter heroes
for destination availability and do not add a selector flag: if the chosen
hero has no legal destination, ordinary mandatory `SelectStep` failure
fizzles the spell with no fallback hero choice.

**Shield:** `CreateEffectStep(ATTACK_IMMUNITY, THIS_ROUND,
basic_attacks_only=True, is_active=True)` bound to the performing spell/card
and caster. Repeated resolution must not create duplicate card-bound effects.

- [ ] Write every §9-§11 path before effect code.
- [ ] Assert Burning Hands victim selection excludes the target via
  `min_range=1`, not merely max-range adjacency.
- [ ] Assert Suggestion offers an in-radius enemy with no exact-3 destination;
  choosing it fizzles without offering a different hero, even when another
  enemy could move. Also cover no enemy, six axes, exact distance, blocked
  path, occupied landing, board edge, topology, and final-step displacement
  prevention.
- [ ] Assert Shield Prepare cancellation, round expiry, copied caster, and
  ordinary-immunity regression.
- [ ] Implement the three effects and run focused/full suites.
- [ ] Suggested commit: `feat: implement Gydion elementary spells`

---

### Task 8: Cross-character integrations, coverage audit, and final gates

**Files:** append interaction tests to the Gydion test files; update this plan
and TDD-path status after implementation; verify client guide.

- [ ] Drive a copied Cantrip end-to-end: unique Gydion owner, different caster,
  caster-routed spell/action inputs, caster stats/position, Gydion spell spent.
- [ ] Drive outer-action repeat versus spell-action repeat and assert event/
  spellbook counts distinguish them.
- [ ] Verify nested context on success, Hold, no legal target, failed mandatory
  step, and persistence resume.
- [ ] Verify ordinary `ResolveCardStep`, NebKher Mind Grip, basic-action
  passives, stat auras, and unrestricted attack immunity regressions.
- [ ] Cross-check every H/U path in the TDD document has a test; leave no
  `xfail` or placeholder registration.
- [ ] Run final gates:

```bash
PYTHONPATH=src uv run pytest tests/ -q
uv run ruff check src/
uv run black --check src/
uv run mypy src/
```

- [ ] Mark both Gydion plan docs implemented with date/test count and record
  any reviewed deviations.
- [ ] Suggested commit: `docs: finalize Gydion first-six-spells implementation`

## Completion definition

The phase is complete only when all six spell primaries and generated
secondaries work through real Gydion access-card flows; prepared identities
remain private; copied/repeated nested actions use the correct source/caster;
Shield's generic immunity extension and Suggestion's existing-filter assembly
have regression coverage; state and
pending steps round-trip; the client guide is current; and all quality gates
pass.
