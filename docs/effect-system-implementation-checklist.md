# Effect System Implementation Checklist

**Source:** `docs/architecture-effect-system-plan.md`
**Status:** Phase 1 Complete, Phase 2 Complete, Phase 3 In Progress
**Approach:** TDD - write tests first, then implementation

---

## Progress Summary

| Phase | Status | Tests Added |
|-------|--------|-------------|
| Phase 1: Foundation | ✅ Complete | 61 tests |
| Phase 2: Effect Lifecycle | ✅ Complete | 15 tests |
| Phase 3: Step Integration | ✅ Complete | 6 tests |
| Phase 4: Effect Creation | ✅ Complete | 3 tests |
| Phase 5: Filter Migration | ✅ Complete | 3 tests |
| Phase 6: Card Implementations | ✅ Complete | 3 tests |

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

## Phase 1: Foundation ✅ COMPLETE

**Completed:** 2026-01-04
**Tests:** 61 new tests added (7 modifier, 22 effect, 27 validation, 5 state integration)
**Files Created:**
- `src/goa2/domain/models/effect.py`
- `src/goa2/engine/validation.py`
- `tests/domain/test_modifier.py`
- `tests/domain/test_effect.py`
- `tests/engine/test_validation.py`

**Files Modified:**
- `src/goa2/domain/models/modifier.py` (NEXT_TURN, source_card_id)
- `src/goa2/domain/state.py` (active_effects, validator, add_effect, get_modifiers_on)

### 1.1 Enhance DurationType

**File:** `src/goa2/domain/models/modifier.py`
**Depends on:** Nothing
**Test file:** `tests/domain/test_modifier.py`

- [x] **Test first:** `test_duration_type_has_next_turn`
  ```python
  def test_duration_type_has_next_turn():
      assert DurationType.NEXT_TURN == "NEXT_TURN"
  ```

- [x] **Implementation:** Add `NEXT_TURN = "NEXT_TURN"` to DurationType enum

---

### 1.2 Enhance Modifier Model

**File:** `src/goa2/domain/models/modifier.py`
**Depends on:** 1.1 DurationType
**Test file:** `tests/domain/test_modifier.py`

- [x] **Test first:** `test_modifier_has_source_card_id`
  ```python
  def test_modifier_has_source_card_id():
      mod = Modifier(
          id="mod_1",
          source_id="hero_1",
          source_card_id="card_123",  # NEW FIELD
          target_id="hero_2",
          status_tag="PREVENT_MOVEMENT",
          duration=DurationType.THIS_TURN,
          created_at_turn=1,
          created_at_round=1
      )
      assert mod.source_card_id == "card_123"
  ```

- [x] **Implementation:** Add `source_card_id: Optional[str] = None` to Modifier

---

### 1.3 Create ValidationResult

**File:** `src/goa2/engine/validation.py` (NEW)
**Depends on:** Nothing
**Test file:** `tests/engine/test_validation.py` (NEW)

- [x] **Test first:** `test_validation_result_allow`
  ```python
  def test_validation_result_allow():
      result = ValidationResult.allow()
      assert result.allowed is True
      assert result.reason == ""
  ```

- [x] **Test:** `test_validation_result_deny`
  ```python
  def test_validation_result_deny():
      result = ValidationResult.deny(
          reason="Movement prevented",
          modifier_ids=["mod_1"],
          source="enemy_hero"
      )
      assert result.allowed is False
      assert result.reason == "Movement prevented"
      assert "mod_1" in result.blocking_modifier_ids
  ```

- [x] **Implementation:** Create ValidationResult class per plan section 3.4

---

### 1.4 Create ActiveEffect Model

**File:** `src/goa2/domain/models/effect.py` (NEW)
**Depends on:** 1.1 DurationType
**Test file:** `tests/domain/test_effect.py` (NEW)

- [x] **Test first:** `test_effect_type_enum`
  ```python
  def test_effect_type_enum():
      assert EffectType.PLACEMENT_PREVENTION == "placement_prevention"
      assert EffectType.MOVEMENT_ZONE == "movement_zone"
  ```

- [x] **Test:** `test_effect_scope_creation`
  ```python
  def test_effect_scope_creation():
      scope = EffectScope(
          shape=Shape.RADIUS,
          range=3,
          origin_id="hero_1",
          affects=AffectsFilter.ENEMY_UNITS
      )
      assert scope.shape == Shape.RADIUS
      assert scope.range == 3
  ```

- [x] **Test:** `test_active_effect_creation`
  ```python
  def test_active_effect_creation():
      effect = ActiveEffect(
          id="eff_1",
          source_id="hero_1",
          source_card_id="card_1",
          effect_type=EffectType.PLACEMENT_PREVENTION,
          scope=EffectScope(shape=Shape.RADIUS, range=3),
          duration=DurationType.THIS_TURN,
          created_at_turn=1,
          created_at_round=1,
          blocks_enemy_actors=True
      )
      assert effect.effect_type == EffectType.PLACEMENT_PREVENTION
  ```

- [x] **Implementation:** Create enums and models per plan section 3.3:
  - `EffectType` enum
  - `AffectsFilter` enum
  - `Shape` enum
  - `EffectScope` model
  - `ActiveEffect` model

---

### 1.5 Create ValidationService (Core Methods Only)

**File:** `src/goa2/engine/validation.py`
**Depends on:** 1.2 Modifier, 1.3 ValidationResult, 1.4 ActiveEffect
**Test file:** `tests/engine/test_validation.py`

#### 1.5.1 Card State Check

- [x] **Test first:** `test_is_card_in_played_state_current_turn`
  ```python
  def test_is_card_in_played_state_current_turn(game_state_with_hero):
      state = game_state_with_hero
      hero = state.get_hero("hero_1")
      card = hero.hand[0]

      # Card in hand - not played
      validator = ValidationService()
      assert validator._is_card_in_played_state(state, "hero_1", card.id) is False

      # Play the card
      hero.play_card(card)
      assert validator._is_card_in_played_state(state, "hero_1", card.id) is True
  ```

- [x] **Test:** `test_is_card_in_played_state_resolved`
  ```python
  def test_is_card_in_played_state_resolved(game_state_with_hero):
      state = game_state_with_hero
      hero = state.get_hero("hero_1")
      card = hero.hand[0]

      hero.play_card(card)
      hero.resolve_current_card()

      validator = ValidationService()
      assert validator._is_card_in_played_state(state, "hero_1", card.id) is True
  ```

- [x] **Implementation:** `_is_card_in_played_state()` method

#### 1.5.2 Modifier Active Check

- [x] **Test first:** `test_modifier_active_passive_duration`
  ```python
  def test_modifier_active_passive_duration(game_state):
      mod = Modifier(
          id="mod_1", source_id="hero_1", target_id="hero_2",
          status_tag="BONUS", duration=DurationType.PASSIVE,
          created_at_turn=1, created_at_round=1
      )
      validator = ValidationService()
      assert validator._is_modifier_active(mod, game_state) is True
  ```

- [x] **Test:** `test_modifier_inactive_when_card_not_played`
  ```python
  def test_modifier_inactive_when_card_not_played(game_state_with_hero):
      state = game_state_with_hero
      hero = state.get_hero("hero_1")
      card = hero.hand[0]  # Card still in hand

      mod = Modifier(
          id="mod_1", source_id="hero_1", source_card_id=card.id,
          target_id="hero_2", status_tag="PREVENT_MOVEMENT",
          duration=DurationType.THIS_TURN,
          created_at_turn=1, created_at_round=1
      )

      validator = ValidationService()
      assert validator._is_modifier_active(mod, state) is False
  ```

- [x] **Test:** `test_modifier_active_this_turn`
- [x] **Test:** `test_modifier_inactive_wrong_turn`
- [x] **Test:** `test_modifier_next_turn_activates_correctly`
- [x] **Test:** `test_modifier_next_turn_turn4_never_activates`

- [x] **Implementation:** `_is_modifier_active()` method

#### 1.5.3 Can Perform Action

- [x] **Test first:** `test_can_perform_action_no_prevention`
  ```python
  def test_can_perform_action_no_prevention(game_state):
      validator = ValidationService()
      result = validator.can_perform_action(
          game_state, "hero_1", ActionType.MOVEMENT
      )
      assert result.allowed is True
  ```

- [x] **Test:** `test_can_perform_action_prevented`
  ```python
  def test_can_perform_action_prevented(game_state):
      game_state.active_modifiers.append(Modifier(
          id="mod_1", source_id="enemy", target_id="hero_1",
          status_tag="PREVENT_MOVEMENT",
          duration=DurationType.PASSIVE,  # Always active for test
          created_at_turn=1, created_at_round=1
      ))

      validator = ValidationService()
      result = validator.can_perform_action(
          game_state, "hero_1", ActionType.MOVEMENT
      )
      assert result.allowed is False
      assert "mod_1" in result.blocking_modifier_ids
  ```

- [x] **Implementation:** `can_perform_action()` method

#### 1.5.4 Can Be Placed

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

---

### 1.6 Integrate ValidationService with GameState

**File:** `src/goa2/domain/state.py`
**Depends on:** 1.5 ValidationService
**Test file:** `tests/domain/test_state.py`

- [x] **Test first:** `test_game_state_has_active_effects`
  ```python
  def test_game_state_has_active_effects():
      state = GameState(...)
      assert hasattr(state, 'active_effects')
      assert state.active_effects == []
  ```

- [x] **Test:** `test_game_state_validator_property`
  ```python
  def test_game_state_validator_property():
      state = GameState(...)
      assert state.validator is not None
      assert isinstance(state.validator, ValidationService)
  ```

- [x] **Test:** `test_game_state_add_effect`
- [x] **Test:** `test_game_state_get_modifiers_on`

- [x] **Implementation:**
  - Add `active_effects: List[ActiveEffect] = Field(default_factory=list)`
  - Add `_validator` private field and `validator` property
  - Add `add_effect()` method
  - Add `get_modifiers_on()` method
  - Update `__init__.py` exports

---

## Phase 1 Checkpoint

Before proceeding to Phase 2, verify:
- [x] All Phase 1 tests pass
- [x] `ValidationService.can_be_placed()` works correctly
- [x] `GameState.validator` property works
- [x] No regressions in existing tests: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 2: Effect Lifecycle ✅ COMPLETE

### 2.1 Create EffectManager

**File:** `src/goa2/engine/effect_manager.py` (New file)
**Depends on:** Phase 1 complete
**Test file:** `tests/engine/test_effect_manager.py` (NEW)

- [x] **Test first:** `test_create_modifier`
  ```python
  def test_create_modifier(game_state):
      from goa2.engine.effect_manager import EffectManager

      mod = EffectManager.create_modifier(
          state=game_state,
          source_id="hero_1",
          target_id="hero_2",
          status_tag="PREVENT_MOVEMENT",
          duration=DurationType.THIS_TURN,
          source_card_id="card_1"
      )

      assert mod in game_state.active_modifiers
      assert mod.source_card_id == "card_1"
  ```

- [x] **Test:** `test_create_effect`
- [x] **Test:** `test_expire_by_card`
- [x] **Test:** `test_expire_modifiers_by_duration`
- [x] **Test:** `test_expire_by_source`

- [x] **Implementation:** EffectManager class with static methods per plan section 4.2

---

### 2.2 Phase Expiration Integration

**File:** `src/goa2/engine/phases.py`
**Depends on:** 2.1 EffectManager
**Test file:** `tests/engine/test_phases.py`

- [x] **Test first:** `test_end_turn_expires_this_turn_modifiers`
  ```python
  def test_end_turn_expires_this_turn_modifiers(game_state):
      game_state.active_modifiers.append(Modifier(
          id="mod_1", source_id="hero_1", target_id="hero_2",
          status_tag="PREVENT_MOVEMENT",
          duration=DurationType.THIS_TURN,
          created_at_turn=1, created_at_round=1
      ))

      end_turn(game_state)

      assert len(game_state.active_modifiers) == 0
  ```

- [x] **Test:** `test_end_round_expires_this_round_effects`
- [x] **Test:** `test_passive_effects_never_expire`

- [x] **Implementation:** Update `end_turn()` and `end_round()` to call EffectManager

---

### 2.3 Lazy Cleanup at Round End

**File:** `src/goa2/engine/phases.py`
**Depends on:** 2.2
**Test file:** `tests/engine/test_phases.py`

- [x] **Test first:** `test_end_round_cleans_stale_card_effects`
  ```python
  def test_end_round_cleans_stale_card_effects(game_state_with_hero):
      state = game_state_with_hero
      hero = state.get_hero("hero_1")
      card = hero.hand[0]

      # Create effect linked to card (card not played)
      state.active_effects.append(ActiveEffect(
          id="eff_1", source_id="hero_1", source_card_id=card.id,
          effect_type=EffectType.PLACEMENT_PREVENTION,
          scope=EffectScope(shape=Shape.GLOBAL),
          duration=DurationType.THIS_ROUND,
          created_at_turn=1, created_at_round=1
      ))

      end_round(state)

      # Effect should be cleaned up (card never played)
      assert len(state.active_effects) == 0
  ```

- [x] **Implementation:** Add stale effect cleanup to `end_round()`

---

## Phase 2 Checkpoint

Before proceeding to Phase 3, verify:
- [x] All Phase 2 tests pass
- [x] Effects expire correctly at turn/round boundaries
- [x] Stale effects (card not played) are cleaned up
- [x] No regressions: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 3: Step Integration

### 3.1 Update PlaceUnitStep (Proof of Concept)

**File:** `src/goa2/engine/steps.py`
**Depends on:** Phase 2 complete
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_place_unit_step_blocked_by_effect`
  ```python
  def test_place_unit_step_blocked_by_effect(game_state_with_heroes):
      state = game_state_with_heroes

      # Blue hero creates placement prevention effect
      state.active_effects.append(ActiveEffect(
          id="eff_1", source_id="blue_hero",
          effect_type=EffectType.PLACEMENT_PREVENTION,
          scope=EffectScope(
              shape=Shape.RADIUS, range=3,
              origin_id="blue_hero",
              affects=AffectsFilter.ENEMY_UNITS
          ),
          duration=DurationType.PASSIVE,
          created_at_turn=1, created_at_round=1,
          blocks_enemy_actors=True
      ))

      # Place blue hero
      state.entity_locations["blue_hero"] = Hex(0, 0, 0)
      # Red hero in radius
      state.entity_locations["red_hero"] = Hex(2, -1, -1)

      # Red hero is current actor
      state.current_actor_id = "red_hero"

      step = PlaceUnitStep(
          unit_id="red_hero",
          target_hex_arg=Hex(3, -2, -1),
          is_mandatory=True
      )

      result = step.resolve(state, {})

      assert result.abort_action is True
  ```

- [x] **Test:** `test_place_unit_step_succeeds_when_no_effect`
- [x] **Test:** `test_place_unit_step_optional_continues_when_blocked`

- [x] **Implementation:** Add validation call to PlaceUnitStep.resolve()

---

### 3.2 Update SwapUnitsStep

**File:** `src/goa2/engine/steps.py`
**Depends on:** 3.1
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_swap_units_step_blocked_by_effect`
- [x] **Implementation:** Add `validator.can_be_swapped()` call

---

### 3.3 Update PushUnitStep

**File:** `src/goa2/engine/steps.py`
**Depends on:** 3.1
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_push_unit_step_blocked_by_effect`
- [x] **Implementation:** Add `validator.can_be_pushed()` call

---

### 3.4 Update MoveUnitStep

**File:** `src/goa2/engine/steps.py`
**Depends on:** 3.1
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_move_unit_step_blocked_by_prevention`
- [x] **Test:** `test_move_unit_step_capped_by_zone_effect`
- [x] **Implementation:** Add `validator.can_move()` call

---

## Phase 3 Checkpoint

Before proceeding to Phase 4, verify:
- [x] All movement/placement steps validate before executing
- [x] Mandatory steps abort when blocked
- [x] Optional steps continue when blocked
- [x] No regressions: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 4: Effect Creation Steps

### 4.1 Create CreateModifierStep

**File:** `src/goa2/engine/steps.py`
**Depends on:** 2.1 EffectManager
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_create_modifier_step_basic`
  ```python
  def test_create_modifier_step_basic(game_state):
      game_state.current_actor_id = "hero_1"

      step = CreateModifierStep(
          target_id="hero_2",
          status_tag="PREVENT_MOVEMENT",
          duration=DurationType.THIS_TURN
      )

      context = {"current_card_id": "card_1"}
      result = step.resolve(game_state, context)

      assert result.is_finished is True
      assert len(game_state.active_modifiers) == 1
      assert game_state.active_modifiers[0].source_card_id == "card_1"
  ```

- [x] **Test:** `test_create_modifier_step_uses_context_key`
- [x] **Test:** `test_create_modifier_step_skipped_when_no_target`

- [x] **Implementation:** CreateModifierStep class per plan section 6.1

---

### 4.2 Create CreateEffectStep

**File:** `src/goa2/engine/steps.py`
**Depends on:** 2.1 EffectManager
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_create_effect_step_basic`
- [x] **Test:** `test_create_effect_step_uses_context_card`

- [x] **Implementation:** CreateEffectStep class per plan section 6.2

---

### 4.3 Update ResolveCardTextStep

**File:** `src/goa2/engine/steps.py`
**Depends on:** 4.1, 4.2
**Test file:** `tests/engine/test_steps.py`

- [x] **Test first:** `test_resolve_card_sets_current_card_id`
  ```python
  def test_resolve_card_sets_current_card_id(game_state_with_hero):
      state = game_state_with_hero
      hero = state.get_hero("hero_1")
      card = hero.hand[0]
      hero.play_card(card)

      state.current_actor_id = "hero_1"

      step = ResolveCardTextStep()
      context = {}
      step.resolve(state, context)

      assert context["current_card_id"] == card.id
  ```

- [x] **Implementation:** Add `context["current_card_id"] = card.id` to resolve()

---

## Phase 4 Checkpoint

Before proceeding to Phase 5, verify:
- [x] CreateModifierStep creates modifiers with card linkage
- [x] CreateEffectStep creates effects with card linkage
- [x] ResolveCardTextStep sets current_card_id in context
- [x] No regressions: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 5: Filter Migration

### 5.1 Create CanBePlacedByActorFilter

**File:** `src/goa2/engine/filters.py`
**Depends on:** Phase 3 complete (ValidationService in use)
**Test file:** `tests/engine/test_filters.py`

- [ ] **Test first:** `test_can_be_placed_filter_allows_when_no_effect`
- [ ] **Test:** `test_can_be_placed_filter_blocks_when_effect_active`

- [ ] **Implementation:** CanBePlacedByActorFilter per plan section 5.2

---

## Phase 5 Checkpoint

Before proceeding to Phase 6, verify:
- [ ] Filters use ValidationService (single source of truth)
- [ ] Selection UI would show correct valid targets
- [ ] No regressions: `PYTHONPATH=src uv run pytest tests/`

---

## Phase 6: Example Card Implementations

### 6.1 Venom Strike (Stat Modifiers)

**File:** `src/goa2/data/heroes/` (appropriate hero file)
**Depends on:** Phase 4 complete
**Test file:** `tests/engine/test_card_effects.py`

- [ ] **Test first:** `test_venom_strike_applies_debuffs`
  ```python
  def test_venom_strike_applies_debuffs(game_with_combat):
      # Setup attack scenario
      # ...

      resolve_card(game, "attacker", "venom_strike")

      # Verify -1 to Attack, Defense, Initiative on victim
      victim_attack = get_computed_stat(state, "victim", StatType.ATTACK)
      assert victim_attack == base_attack - 1
  ```

- [ ] **Implementation:** VenomStrikeEffect per plan section 7.4

---

### 6.2 Slippery Ground (Movement Zone)

**File:** `src/goa2/data/heroes/`
**Depends on:** Phase 4 complete
**Test file:** `tests/engine/test_card_effects.py`

- [ ] **Test first:** `test_slippery_ground_limits_movement`
- [ ] **Implementation:** SlipperyGroundEffect per plan section 7.2

---

### 6.3 Magnetic Dagger (Placement Prevention)

**File:** `src/goa2/data/heroes/`
**Depends on:** Phase 4 complete
**Test file:** `tests/engine/test_card_effects.py`

- [ ] **Test first:** `test_magnetic_dagger_prevents_placement`
- [ ] **Implementation:** MagneticDaggerEffect per plan section 7.1

---

## Final Verification

- [ ] All tests pass: `PYTHONPATH=src uv run pytest --cov=goa2 tests/`
- [ ] Code quality: `uv run ruff check src/`
- [ ] Type check: `uv run mypy src/`
- [ ] Demo works: `PYTHONPATH=src uv run python -m goa2.scripts.demo_step_engine`

---

## Files Created/Modified Summary

### New Files
- `src/goa2/domain/models/effect.py`
- `src/goa2/engine/validation.py`
- `tests/engine/test_validation.py`
- `tests/domain/test_effect.py`
- `tests/engine/test_effect_manager.py`
- `src/goa2/engine/effect_manager.py`

### Modified Files
- `src/goa2/domain/models/modifier.py` - Add NEXT_TURN, source_card_id
- `src/goa2/domain/models/__init__.py` - Export new models
- `src/goa2/domain/state.py` - Add active_effects, validator
- `src/goa2/engine/effects.py` - Add EffectManager (Note: implemented in separate file `effect_manager.py`)
- `src/goa2/engine/steps.py` - Add validation, CreateModifierStep, CreateEffectStep
- `src/goa2/engine/phases.py` - Add expiration calls
- `src/goa2/engine/filters.py` - Add CanBePlacedByActorFilter