# Character Effect Testing Strategy Plan

This plan tracks the migration to a dedicated character effect testing architecture.

Use this document as the session handoff. At the start of a session:

1. Find the first unchecked task in the current phase.
2. Read the task's scope and stop condition.
3. Do only that task unless the task explicitly says to continue.
4. Mark completed items with `[x]`.
5. Add notes under "Session Notes" when decisions, blockers, or follow-up work appear.

Do not migrate unrelated legacy tests opportunistically. Keep each session small enough that tests can be run and failures understood before stopping.

## Current Status

- [x] Phase 1: Foundation
- [x] Phase 2: Adoption Standard
- [ ] Phase 3: Legacy Migration

## Phase 1: Foundation

Goal: create the helper package and prove the API by porting two representative effect suites.

Stop this phase when:

- `tests/engine/effects/` exists with builder, runner, assertions, and local fixtures.
- `liquid_leap` and `static_barrier` have representative tests using the new helpers.
- Relevant engine tests pass.
- Any unresolved helper limitations are recorded in this document.

### Task 1.1: Inspect Existing Effect Test Patterns

Scope:

- [x] Read existing effect/card tests for common setup patterns.
- [x] Identify where board/team/hero/card setup is duplicated.
- [x] Identify how tests currently push steps and provide input.
- [x] Identify existing fixtures worth reusing rather than replacing immediately.

Suggested files to inspect:

- `tests/engine/`
- `tests/engine/test_*effect*.py`
- `tests/engine/test_*card*.py`
- `tests/engine/test_*liquid*leap*.py`
- `tests/engine/test_*static*barrier*.py`

Deliverable:

- [x] Add a short note under "Session Notes" summarizing the current patterns and the first helper API shape.

Stop condition:

- Stop after notes are written. Do not implement helpers in the same task unless explicitly continuing.

### Task 1.2: Create Effects Test Package Skeleton

Scope:

- [x] Create `tests/engine/effects/`.
- [x] Create `tests/engine/effects/conftest.py`.
- [x] Create `tests/engine/effects/builders.py`.
- [x] Create `tests/engine/effects/runner.py`.
- [x] Create `tests/engine/effects/assertions.py`.
- [x] Create `tests/engine/effects/cases/`.
- [x] Add package/readme comments only where they clarify intended usage.

Deliverable:

- [x] Empty or minimal helper modules import cleanly.

Verification:

- [x] Run targeted collection for the new package, for example:

```bash
PYTHONPATH=src uv run pytest tests/engine/effects/ --collect-only -q
```

Stop condition:

- Stop after the skeleton imports/collects successfully.

### Task 1.3: Implement Scenario Builder V1

Scope:

- [x] Implement `EffectScenarioBuilder`.
- [x] Add board factory: `line_board(length=6)`.
- [ ] Add entity helpers:
  - [x] `.hero(hero_id, team, at, current_card=None)`
  - [x] `.enemy_hero(hero_id, at, team=None)`
  - [x] `.enemy_minion(minion_id, at, team=None)`
  - [x] `.with_actor(hero_id)`
  - [x] `.with_card(hero_id, card_id)`
  - [x] `.build()`
- [x] Ensure entities are placed through `state.place_entity()`.
- [x] Ensure teams and turn/actor fields are wired consistently with existing tests.
- [x] Keep defaults strong but explicit enough that failures are understandable.

Deliverable:

- [x] Builder can create a minimal state with an actor, card, enemy hero, and enemy minion.

Verification:

- [x] Add or run a small helper test if needed.
- [x] Run the targeted tests touching the builder.

Stop condition:

- Stop after builder V1 is usable for `liquid_leap` and `static_barrier` scenarios. Do not generalize beyond those needs.

### Task 1.4: Implement Effect Runner V1

Scope:

- [x] Implement `run_card(state, hero_id)` returning `EffectRun`.
- [x] Wrap card execution through the same public/engine path used by existing tests.
- [ ] Implement chainable methods:
  - [x] `.expect_input(input_type)`
  - [x] `.choose(value)`
  - [x] `.skip()`
  - [x] `.confirm()`
  - [x] `.finish()`
- [ ] Include useful failure output:
  - [x] current stack types
  - [x] execution context keys/values where safe
  - [x] latest input request
  - [x] emitted event types
- [x] Avoid direct stack mutation from tests outside this helper.

Deliverable:

- [x] Runner can drive an input-based effect through at least one prompt and completion.

Verification:

- [x] Run targeted tests touching the runner.

Stop condition:

- Stop after runner V1 supports the first two migrated effects. Do not add broad DSL methods until a test needs them.

### Task 1.5: Implement Assertion Helpers V1

Scope:

- [x] Implement `assert_position(state, entity_id, coords)`.
- [x] Implement `assert_effect_active(state, effect_type, source_id=None)`.
- [x] Implement `assert_valid_options(req, contains=None, excludes=None)`.
- [x] Implement `assert_event_emitted(state, event_type, **fields)`.
- [x] Make assertion failures read as behavior failures, not fixture failures.

Deliverable:

- [x] Assertion helpers are used by at least one migrated test.

Verification:

- [x] Run targeted tests touching assertions.

Stop condition:

- Stop after helpers cover `liquid_leap` and `static_barrier` expectations.

### Task 1.6: Port Liquid Leap Representative Tests

Scope:

- [x] Create `tests/engine/effects/cases/test_liquid_leap_contract.py`.
- [x] Express tests in Given/When/Then style using builder, runner, and assertions.
- [x] Cover expected target/input behavior.
- [x] Cover movement or placement outcome.
- [x] Cover required event emission if the effect changes observable state.
- [x] Check both positive and negative valid options for input-driven prompts.

Deliverable:

- [x] Liquid Leap has representative contract coverage in the new package.
- [x] Legacy tests remain in place unless a direct duplicate should be removed with clear parity.

Verification:

- [x] Run the new Liquid Leap test module.
- [x] Run relevant existing Liquid Leap tests.

Stop condition:

- Stop after Liquid Leap tests pass and any helper gaps are noted.

### Task 1.7: Port Static Barrier Representative Tests

Scope:

- [x] Create `tests/engine/effects/cases/test_static_barrier_contract.py`.
- [x] Express tests in Given/When/Then style using builder, runner, and assertions.
- [x] Cover activation behavior.
- [x] Cover active effect/modifier state.
- [x] Cover duration or expiration behavior if practical at contract level.
- [x] Check emitted events if activation is observable to clients.

Deliverable:

- [x] Static Barrier has representative contract coverage in the new package.
- [x] Helper API is validated against both movement-like and active-effect-like behavior.

Verification:

- [x] Run the new Static Barrier test module.
- [x] Run relevant existing Static Barrier tests.

Stop condition:

- Stop after Static Barrier tests pass and any helper gaps are noted.

### Task 1.8: Phase 1 Verification

Scope:

- [x] Run all new effect tests.
- [x] Run the full engine test suite if feasible.
- [x] Run server tests only if client-facing contracts were touched. No client-facing contracts were touched.
- [x] Review helper APIs for over-generalization or unclear names.
- [x] Update this document with Phase 1 results.

Suggested commands:

```bash
PYTHONPATH=src uv run pytest tests/engine/effects/ -q
PYTHONPATH=src uv run pytest tests/engine/ -q
PYTHONPATH=src uv run pytest tests/server/ -q
```

Deliverable:

- [x] Phase 1 marked complete if verification passes.

Stop condition:

- Stop after Phase 1 is marked complete or blockers are recorded.

## Phase 2: Adoption Standard

Goal: make the new pattern the standard for new and touched character effect tests without forcing a risky mass migration.

Stop this phase when:

- Pytest markers exist and are documented.
- Test authoring guidance points new effect tests to the helper package.
- New/touched effect tests have a clear review checklist.

### Task 2.1: Add Pytest Markers

Scope:

- [x] Add `effect_contract` marker.
- [x] Add `effect_flow` marker.
- [x] Ensure marker registration lives in the existing pytest configuration location.
- [x] Mark the new Liquid Leap and Static Barrier contract tests.

Deliverable:

- [x] `pytest --markers` shows the new markers.
- [x] No unknown-marker warnings.

Verification:

```bash
PYTHONPATH=src uv run pytest tests/engine/effects/ -q
```

Stop condition:

- Stop after marker registration and marked tests pass.

### Task 2.2: Document Effect Test Conventions

Scope:

- [x] Add a concise testing convention section to the best existing doc.
- [x] Include the package path and intended helper usage.
- [ ] Include the quality gates:
  - [x] no direct stack mutation in effect tests except through runner DSL
  - [x] assert at least one board/entity, active effect, or event outcome
  - [x] input-driven effects assert prompt type and valid options
  - [x] use `effect_contract` or `effect_flow` markers
- [x] Mention legacy tests may remain until touched.

Candidate docs:

- `docs/card_effects_guidelines.md`
- `docs/EFFECT_AUTHOR_REFERENCE.md`
- `AGENTS.md`

Deliverable:

- [x] Future sessions can find the convention without reading this plan.

Stop condition:

- Stop after documentation is updated and reviewed for consistency.

### Task 2.3: Add Review Checklist Note

Scope:

- [x] Add a short checklist item wherever test review guidance belongs.
- [x] State that new character effect tests should use `tests/engine/effects/` helpers unless there is a documented reason not to.

Deliverable:

- [x] The convention is visible during review.

Stop condition:

- Stop after the checklist note is added.

### Task 2.4: Phase 2 Verification

Scope:

- [x] Run new effect tests.
- [x] Run docs-adjacent checks if the repo has any.
- [x] Update this document with Phase 2 results.

Deliverable:

- [x] Phase 2 marked complete if verification passes.

Stop condition:

- Stop after Phase 2 is marked complete or blockers are recorded.

## Phase 3: Legacy Migration

Goal: gradually migrate remaining legacy character effect tests while preserving coverage and avoiding broad unrelated churn.

Stop this phase when:

- Remaining effect tests either use the new architecture or have a documented reason to stay legacy.
- Duplicated fixtures made obsolete by migration are removed.
- Engine tests pass.

### Task 3.1: Inventory Legacy Effect Tests

Scope:

- [ ] List all legacy character effect tests.
- [ ] Group them by effect.
- [ ] Classify each as contract, flow, or regression.
- [ ] Identify duplicated setup helpers that can be removed after migration.

Deliverable:

- [ ] Add the inventory under "Legacy Migration Inventory".

Stop condition:

- Stop after inventory is complete. Do not migrate tests in the same task unless explicitly continuing.

### Task 3.2: Migrate One Effect Module

Use this task repeatedly, one effect at a time.

Scope:

- [ ] Pick one effect from the inventory.
- [ ] Create or update the matching file under `tests/engine/effects/cases/`.
- [ ] Re-express setup through `EffectScenarioBuilder`.
- [ ] Re-express stack/input flow through `EffectRun`.
- [ ] Use assertion helpers for outcome checks.
- [ ] Preserve regression names and issue references.
- [ ] Remove only legacy tests that are clearly covered by the new tests.

Deliverable:

- [ ] One effect's tests migrated or explicitly deferred with a reason.

Verification:

- [ ] Run the migrated module.
- [ ] Run the old module if any tests remain.
- [ ] Run `tests/engine/effects/`.

Stop condition:

- Stop after one effect migration is complete and passing.

### Task 3.3: Remove Obsolete Duplicated Fixtures

Scope:

- [ ] Remove custom fixtures that are no longer used after migration.
- [ ] Keep shared fixtures that still serve non-effect tests.
- [ ] Prefer small removals with test verification after each batch.

Deliverable:

- [ ] Obsolete fixture duplication reduced without changing test behavior.

Verification:

- [ ] Run affected test modules.
- [ ] Run `tests/engine/ -q` when practical.

Stop condition:

- Stop after one removal batch is complete and passing.

### Task 3.4: Phase 3 Verification

Scope:

- [ ] Run all new effect tests.
- [ ] Run full engine tests.
- [ ] Update this document with final migration status.

Suggested commands:

```bash
PYTHONPATH=src uv run pytest tests/engine/effects/ -q
PYTHONPATH=src uv run pytest tests/engine/ -q
```

Deliverable:

- [ ] Phase 3 marked complete if verification passes.

Stop condition:

- Stop after Phase 3 is marked complete or blockers are recorded.

## Legacy Migration Inventory

Add entries during Task 3.1.

| Effect | Existing test files | Target category | Migration status | Notes |
| --- | --- | --- | --- | --- |
| Liquid Leap | `tests/engine/test_arien_liquid_leap.py` | Contract | Representative port complete | New tests in `tests/engine/effects/cases/test_liquid_leap_contract.py`; legacy tests remain. |
| Static Barrier | `tests/engine/test_wasp_static_barrier.py` | Contract / Flow | Representative port complete | New tests in `tests/engine/effects/cases/test_static_barrier_contract.py`; broad legacy suite remains. |

## Helper API Decisions

Record decisions here when the builder/runner/assertions API changes.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-05-08 | `run_card(..., finalize_turn=True)` is supported for effects that only activate during `FinalizeHeroTurnStep`. | Static Barrier is created dormant during card text resolution and becomes active only when the source card resolves. |
| 2026-05-08 | Register `effect_contract` and `effect_flow` during Phase 1. | Phase 1 tests already use `effect_contract`; registering markers avoids warning noise in verification. |
| 2026-05-08 | Start with V1 helpers only for Liquid Leap and Static Barrier. | Avoid over-generalizing before the first representative ports. |

## Session Notes

Add newest notes at the top.

### 2026-05-08 Phase 2 Complete

- Added the character effect test convention to `docs/card_effects_guidelines.md`.
- Added the review/session checklist note to `AGENTS.md` under "Writing Card Effects".
- Phase 2 Task 2.1 was already completed during Phase 1 because the new tests used `effect_contract`.
- Verification passed:
  - `PYTHONPATH=src uv run pytest --markers` -> `effect_contract` and `effect_flow` listed
  - `PYTHONPATH=src uv run pytest tests/engine/effects/ -q` -> 4 passed

Current next task for a new session: start Phase 3 Task 3.1, inventorying legacy effect tests before migrating anything.

### 2026-05-08 Phase 1 Complete

- Added `tests/engine/effects/` with `builders.py`, `runner.py`, `assertions.py`, local `conftest.py`, and case modules.
- Current helper API covers `EffectScenarioBuilder`, canonical `liquid_leap` / `static_barrier` card factories, `run_card()`, chainable input driving, and intent-level assertions.
- Ported representative Liquid Leap contract tests for valid hex filtering, placement outcome, and `UNIT_PLACED` event emission.
- Ported representative Static Barrier contract tests for full-turn activation, active effect fields/duration, `EFFECT_CREATED` event emission, and enemy movement option blocking.
- Added marker registration in `pyproject.toml` ahead of Phase 2 to keep Phase 1 verification warning-free.
- Fixed `tests/engine/test_arien_liquid_leap.py` to explicitly import Arien effect registration when run directly.
- Verification passed:
  - `PYTHONPATH=src uv run pytest tests/engine/effects/ -q` -> 4 passed
  - `PYTHONPATH=src uv run pytest tests/engine/test_arien_liquid_leap.py tests/engine/test_wasp_static_barrier.py -q` -> 16 passed
  - `PYTHONPATH=src uv run pytest tests/engine/ -q` -> 1185 passed

### 2026-05-08 Initial Plan

- Created this implementation plan from the Character Effect Testing Strategy.
- Recommended sequence is three phases: foundation, adoption standard, and legacy migration.
- Each task has its own stop condition so a future session knows when to pause instead of expanding scope.
