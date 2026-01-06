# Effect System Implementation Checklist

**Source:** `docs/architecture-effect-system-plan.md`
**Status:** ✅ COMPLETE (as of 2026-01-05)
**Approach:** TDD - write tests first, then implementation

> [!NOTE]
> This checklist has been updated to reflect implementation status.
> - `[x]` = Completed
> - `[ ]` = Not implemented (deferred or out of scope)
> - `[~]` = Partially implemented or deviated from plan

---

## Implementation Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Foundation | ✅ Complete | All models, ValidationService, GameState integration |
| Phase 2: Effect Lifecycle | ✅ Complete | EffectManager in separate file (`effect_manager.py`) |
| Phase 3: Step Integration | ✅ Complete | All steps validate via ValidationService |
| Phase 4: Effect Creation | ✅ Complete | CreateModifierStep, CreateEffectStep, context card |
| Phase 5: Filter Migration | ✅ Complete | CanBePlacedByActorFilter implemented |
| Phase 6: Card Examples | ✅ Complete | venom_strike, slippery_ground, magnetic_dagger |

### Deviations from Plan

1. **EffectManager location:** Created in `src/goa2/engine/effect_manager.py` instead of adding to `effects.py`
2. **FORCED_MOVEMENT effect type:** Not implemented - better as a Step (like `PushUnitStep`) since it's immediate, not persistent
3. **Frontend helper methods:** `can_fast_travel()`, `get_effects_at_location()`, `get_valid_placement_targets()`, `get_blocked_units_for_placement()` not implemented yet

---

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PHASE 1: FOUNDATION                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐                                                       │
│  │ 1. DurationType  │ ◄── No dependencies                                   │
│  │    (enhance)     │                                                       │
│  └────────┬─────────┘                                                       │
│           │                                                                 │
│           ▼                                                                 │
│  ┌──────────────────┐    ┌──────────────────┐                              │
│  │ 2. Modifier      │    │ 3. ValidationResult│ ◄── No dependencies        │
│  │    (enhance)     │    │    (new)          │                              │
│  └────────┬─────────┘    └────────┬─────────┘                              │
│           │                       │                                         │
│           ▼                       │                                         │
│  ┌──────────────────┐             │                                         │
│  │ 4. ActiveEffect  │             │                                         │
│  │    (new)         │             │                                         │
│  └────────┬─────────┘             │                                         │
│           │                       │                                         │
│           └───────────┬───────────┘                                         │
│                       ▼                                                     │
│              ┌──────────────────┐                                           │
│              │ 5. ValidationSvc │                                           │
│              │    (new)         │                                           │
│              └────────┬─────────┘                                           │
│                       │                                                     │
│                       ▼                                                     │
│              ┌──────────────────┐                                           │
│              │ 6. GameState     │                                           │
│              │    (enhance)     │                                           │
│              └──────────────────┘                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 2: EFFECT LIFECYCLE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐                                                       │
│  │ 7. EffectManager │ ◄── Depends on: Modifier, ActiveEffect, GameState    │
│  │    (new)         │                                                       │
│  └────────┬─────────┘                                                       │
│           │                                                                 │
│           ▼                                                                 │
│  ┌──────────────────┐    ┌──────────────────┐                              │
│  │ 8. phases.py     │    │ 9. Card retrieval│                              │
│  │    (expiration)  │    │    hooks         │                              │
│  └──────────────────┘    └──────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 3: STEP INTEGRATION                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐                                                       │
│  │10. PlaceUnitStep │ ◄── First step to validate (proof of concept)        │
│  └────────┬─────────┘                                                       │
│           │                                                                 │
│           ▼                                                                 │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │11. SwapUnitsStep │    │12. PushUnitStep  │    │13. MoveUnitStep  │      │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          PHASE 4: EFFECT CREATION                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐    ┌──────────────────┐                              │
│  │14. CreateModifier│    │15. CreateEffect  │ ◄── Depend on EffectManager  │
│  │    Step (new)    │    │    Step (new)    │                              │
│  └────────┬─────────┘    └────────┬─────────┘                              │
│           │                       │                                         │
│           └───────────┬───────────┘                                         │
│                       ▼                                                     │
│              ┌──────────────────┐                                           │
│              │16. ResolveCard   │                                           │
│              │    (set card_id) │                                           │
│              └──────────────────┘                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          PHASE 5: FILTER MIGRATION                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐                                                       │
│  │17. CanBePlaced   │ ◄── Wraps ValidationService                          │
│  │    Filter (new)  │                                                       │
│  └──────────────────┘                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE 6: CARD IMPLEMENTATIONS                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │18. Venom Strike  │    │19. Slippery      │    │20. Magnetic      │      │
│  │    (stat mod)    │    │    Ground (zone) │    │    Dagger (area) │      │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Pre-Implementation Decision

**Card-State Expiration Mechanism:** Use **Option B (Lazy Expiration)**

Rationale:
- ValidationService already checks card state on every query
- Simpler implementation (no callbacks/events on Hero)
- Cleanup at phase boundaries prevents memory bloat
- Effects remain in lists but are correctly filtered

---

## Phase 1: Foundation ✅

### 1.1 Enhance DurationType ✅

**File:** `src/goa2/domain/models/modifier.py`
**Depends on:** Nothing
**Test file:** `tests/domain/test_modifier.py`

- [x] **Test first:** `test_duration_type_has_next_turn`
- [x] **Implementation:** Add `NEXT_TURN = "NEXT_TURN"` to DurationType enum

---

### 1.2 Enhance Modifier Model ✅

**File:** `src/goa2/domain/models/modifier.py`
**Depends on:** 1.1 DurationType
**Test file:** `tests/domain/test_modifier.py`

- [x] **Test first:** `test_modifier_has_source_card_id`
- [x] **Implementation:** Add `source_card_id: Optional[str] = None` to Modifier

---

### 1.3 Create ValidationResult ✅

**File:** `src/goa2/engine/validation.py` (NEW)
**Depends on:** Nothing
**Test file:** `tests/engine/test_validation.py` (NEW)

- [x] **Test first:** `test_validation_result_allow`
- [x] **Test:** `test_validation_result_deny`
- [x] **Implementation:** Create ValidationResult class per plan section 3.4

---

### 1.4 Create ActiveEffect Model ✅

**File:** `src/goa2/domain/models/effect.py` (NEW)
**Depends on:** 1.1 DurationType
**Test file:** `tests/domain/test_effect.py` (NEW)

- [x] **Test first:** `test_effect_type_enum`
- [x] **Test:** `test_effect_scope_creation`
- [x] **Test:** `test_active_effect_creation`
- [x] **Implementation:** Create enums and models per plan section 3.3:
  - `EffectType` enum (4 types: PLACEMENT_PREVENTION, MOVEMENT_ZONE, TARGET_PREVENTION, AREA_STAT_MODIFIER)
  - `AffectsFilter` enum
  - `Shape` enum
  - `EffectScope` model
  - `ActiveEffect` model

> [!NOTE]
> `FORCED_MOVEMENT` effect type was not implemented - it's better as a Step since it's an immediate action, not a persistent effect.

---

### 1.5 Create ValidationService (Core Methods Only) ✅

**File:** `src/goa2/engine/validation.py`
**Depends on:** 1.2 Modifier, 1.3 ValidationResult, 1.4 ActiveEffect
**Test file:** `tests/engine/test_validation.py`

#### 1.5.1 Card State Check ✅

- [x] **Test first:** `test_is_card_in_played_state_current_turn`
- [x] **Test:** `test_is_card_in_played_state_resolved`
- [x] **Implementation:** `_is_card_in_played_state()` method

#### 1.5.2 Modifier Active Check ✅

- [x] **Test first:** `test_modifier_active_passive_duration`
- [x] **Test:** `test_modifier_inactive_when_card_not_played`
- [x] **Test:** `test_modifier_active_this_turn`
- [x] **Test:** `test_modifier_inactive_wrong_turn`
- [x] **Test:** `test_modifier_next_turn_activates_correctly`
- [x] **Test:** `test_modifier_next_turn_turn4_never_activates`
- [x] **Implementation:** `_is_modifier_active()` method

#### 1.5.3 Can Perform Action ✅

- [x] **Test first:** `test_can_perform_action_no_prevention`
- [x] **Test:** `test_can_perform_action_prevented`
- [x] **Implementation:** `can_perform_action()` method

#### 1.5.4 Can Be Placed ✅

- [x] **Test first:** `test_can_be_placed_no_effects`
- [x] **Test:** `test_can_be_placed_blocked_by_status_tag`
- [x] **Test:** `test_can_be_placed_blocked_by_spatial_effect`
- [x] **Test:** `test_can_be_placed_friendly_not_blocked`
- [x] **Implementation:** `can_be_placed()` method with helper methods:
  - `_is_in_scope()`
  - `_hex_in_scope()`
  - `_get_origin_hex()`
  - `_matches_affects_filter()`
  - `_actor_blocked_by_effect()`

#### 1.5.5 Frontend Helper Methods (Not Implemented)

- [ ] `can_fast_travel()` - deferred
- [ ] `get_effects_at_location()` - deferred
- [ ] `get_valid_placement_targets()` - deferred for frontend integration
- [ ] `get_blocked_units_for_placement()` - deferred for frontend integration

---

### 1.6 Integrate ValidationService with GameState ✅

**File:** `src/goa2/domain/state.py`
**Depends on:** 1.5 ValidationService
**Test file:** `tests/domain/test_state.py`

- [x] **Test first:** `test_game_state_has_active_effects`
- [x] **Test:** `test_game_state_validator_property`
- [x] **Test:** `test_game_state_add_effect`
- [x] **Test:** `test_game_state_get_modifiers_on`
- [x] **Implementation:**
  - Add `active_effects: List[ActiveEffect] = Field(default_factory=list)`
  - Add `_validator` private field and `validator` property
  - Add `add_effect()` method
  - Add `get_modifiers_on()` method
  - Update `__init__.py` exports

---

## Phase 1 Checkpoint ✅

- [x] All Phase 1 tests pass
- [x] `ValidationService.can_be_placed()` works correctly
- [x] `GameState.validator` property works
- [x] No regressions in existing tests: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 2: Effect Lifecycle ✅

### 2.1 Create EffectManager ✅

**File:** `src/goa2/engine/effect_manager.py` (NEW - deviated from plan)
**Depends on:** Phase 1 complete
**Test file:** `tests/engine/test_effect_manager.py` (NEW)

> [!NOTE]
> EffectManager was created in a separate file `effect_manager.py` instead of adding to `effects.py` for better modularity.

- [x] **Test first:** `test_create_modifier`
- [x] **Test:** `test_create_effect`
- [x] **Test:** `test_expire_by_card`
- [x] **Test:** `test_expire_modifiers_by_duration`
- [x] **Test:** `test_expire_by_source`
- [x] **Implementation:** EffectManager class with static methods per plan section 4.2

---

### 2.2 Phase Expiration Integration ✅

**File:** `src/goa2/engine/phases.py`
**Depends on:** 2.1 EffectManager
**Test file:** `tests/engine/test_phases.py`

- [x] **Test first:** `test_end_turn_expires_this_turn_modifiers`
- [x] **Test:** `test_end_round_expires_this_round_effects`
- [x] **Test:** `test_passive_effects_never_expire`
- [x] **Implementation:** Update `end_turn()` and `end_round()` to call EffectManager

---

### 2.3 Lazy Cleanup at Round End ✅

**File:** `src/goa2/engine/phases.py`
**Depends on:** 2.2
**Test file:** `tests/engine/test_phases.py`

- [x] **Test first:** `test_end_round_cleans_stale_card_effects`
- [x] **Implementation:** Add stale effect cleanup to `end_round()` via `EffectManager.cleanup_stale_effects()`

---

## Phase 2 Checkpoint ✅

- [x] All Phase 2 tests pass
- [x] Effects expire correctly at turn/round boundaries
- [x] Stale effects (card not played) are cleaned up
- [x] No regressions: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 3: Step Integration ✅

### 3.1 Update PlaceUnitStep (Proof of Concept) ✅

**File:** `src/goa2/engine/steps.py`
**Depends on:** Phase 2 complete
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_place_unit_step_blocked_by_effect`
- [x] **Test:** `test_place_unit_step_succeeds_when_no_effect`
- [x] **Test:** `test_place_unit_step_optional_continues_when_blocked`
- [x] **Implementation:** Add validation call to PlaceUnitStep.resolve() via `validator.can_be_placed()`

---

### 3.2 Update SwapUnitsStep ✅

**File:** `src/goa2/engine/steps.py`
**Depends on:** 3.1
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_swap_units_step_blocked_by_effect`
- [x] **Implementation:** Add `validator.can_be_swapped()` call

---

### 3.3 Update PushUnitStep ✅

**File:** `src/goa2/engine/steps.py`
**Depends on:** 3.1
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_push_unit_step_blocked_by_effect`
- [x] **Implementation:** Add `validator.can_be_pushed()` call

---

### 3.4 Update MoveUnitStep ✅

**File:** `src/goa2/engine/steps.py`
**Depends on:** 3.1
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_move_unit_step_blocked_by_prevention`
- [x] **Test:** `test_move_unit_step_capped_by_zone_effect`
- [x] **Implementation:** Add `validator.can_move()` call

---

## Phase 3 Checkpoint ✅

- [x] All movement/placement steps validate before executing
- [x] Mandatory steps abort when blocked
- [x] Optional steps continue when blocked
- [x] No regressions: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 4: Effect Creation Steps ✅

### 4.1 Create CreateModifierStep ✅

**File:** `src/goa2/engine/steps.py`
**Depends on:** 2.1 EffectManager
**Test file:** `tests/engine/test_effect_creation_steps.py` (NEW - additional test file)

- [x] **Test first:** `test_create_modifier_step_basic`
- [x] **Test:** `test_create_modifier_step_uses_context_key`
- [x] **Test:** `test_create_modifier_step_skipped_when_no_target`
- [x] **Implementation:** CreateModifierStep class per plan section 6.1

---

### 4.2 Create CreateEffectStep ✅

**File:** `src/goa2/engine/steps.py`
**Depends on:** 2.1 EffectManager
**Test file:** `tests/engine/test_effect_creation_steps.py`

- [x] **Test first:** `test_create_effect_step_basic`
- [x] **Test:** `test_create_effect_step_uses_context_card`
- [x] **Implementation:** CreateEffectStep class per plan section 6.2

---

### 4.3 Update ResolveCardTextStep ✅

**File:** `src/goa2/engine/steps.py`
**Depends on:** 4.1, 4.2
**Test file:** `tests/engine/test_effect_creation_steps.py`

- [x] **Test first:** `test_resolve_card_sets_current_card_id`
- [x] **Implementation:** Add `context["current_card_id"] = card.id` to resolve()

---

## Phase 4 Checkpoint ✅

- [x] CreateModifierStep creates modifiers with card linkage
- [x] CreateEffectStep creates effects with card linkage
- [x] ResolveCardTextStep sets current_card_id in context
- [x] No regressions: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 5: Filter Migration ✅

### 5.1 Create CanBePlacedByActorFilter ✅

**File:** `src/goa2/engine/filters.py`
**Depends on:** Phase 3 complete (ValidationService in use)
**Test file:** `tests/engine/test_filters.py`

- [x] **Test first:** `test_can_be_placed_filter_allows_when_no_effect`
- [x] **Test:** `test_can_be_placed_filter_blocks_when_effect_active`
- [x] **Implementation:** CanBePlacedByActorFilter per plan section 5.2

---

## Phase 5 Checkpoint ✅

- [x] Filters use ValidationService (single source of truth)
- [x] Selection UI would show correct valid targets
- [x] No regressions: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 6: Example Card Implementations ✅

### 6.1 Venom Strike (Stat Modifiers) ✅

**File:** `src/goa2/scripts/rogue_effects.py`
**Depends on:** Phase 4 complete
**Test file:** `tests/engine/test_rogue_effects.py`

- [x] **Test first:** `test_venom_strike_applies_debuffs`
- [x] **Implementation:** VenomStrikeEffect via `@register_effect("venom_strike")`

---

### 6.2 Slippery Ground (Movement Zone) ✅

**File:** `src/goa2/scripts/rogue_effects.py` and `src/goa2/data/heroes/arien.py`
**Depends on:** Phase 4 complete
**Test file:** `tests/engine/test_rogue_effects.py`

- [x] **Test first:** `test_slippery_ground_limits_movement`
- [x] **Implementation:** SlipperyGroundEffect via `@register_effect("slippery_ground")`

---

### 6.3 Magnetic Dagger (Placement Prevention) ✅

**File:** `src/goa2/scripts/rogue_effects.py`
**Depends on:** Phase 4 complete
**Test file:** `tests/engine/test_rogue_effects.py`

- [x] **Test first:** `test_magnetic_dagger_prevents_placement`
- [x] **Implementation:** MagneticDaggerEffect via `@register_effect("magnetic_dagger")`

---

## Final Verification ✅

- [x] All tests pass: `PYTHONPATH=src uv run pytest --cov=goa2 tests/`
- [x] Code quality: `uv run ruff check src/`
- [x] Type check: `uv run mypy src/`
- [x] Demo works: `PYTHONPATH=src uv run python -m goa2.scripts.demo_step_engine`

---

## Files Created/Modified Summary

### New Files ✅
- `src/goa2/domain/models/effect.py` ✅
- `src/goa2/engine/validation.py` ✅
- `src/goa2/engine/effect_manager.py` ✅ (deviated: separate file instead of `effects.py`)
- `tests/engine/test_validation.py` ✅
- `tests/domain/test_effect.py` ✅
- `tests/engine/test_effect_manager.py` ✅
- `tests/engine/test_effect_creation_steps.py` ✅ (additional)

### Modified Files ✅
- `src/goa2/domain/models/modifier.py` - Add NEXT_TURN, source_card_id ✅
- `src/goa2/domain/models/__init__.py` - Export new models ✅
- `src/goa2/domain/state.py` - Add active_effects, validator ✅
- `src/goa2/engine/steps.py` - Add validation, CreateModifierStep, CreateEffectStep ✅
- `src/goa2/engine/phases.py` - Add expiration calls ✅
- `src/goa2/engine/filters.py` - Add CanBePlacedByActorFilter ✅
