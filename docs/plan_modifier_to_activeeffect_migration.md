# Migration Plan: Modifiers to ActiveEffects + Markers

## Overview

This document outlines the plan to migrate from the dual `Modifier`/`ActiveEffect` system to a unified `ActiveEffect`-only architecture, with a new `Marker` system for persistent hero debuffs.

### Why This Change?

1. **Modifiers are redundant**: Everything a `Modifier` does can be achieved with `ActiveEffect` using `Shape.POINT`
2. **Card-based activation is rarely needed**: Most effects rely on duration or markers, not card state
3. **Markers are first-class in the board game**: Markers are physical tokens with singleton semantics - our code should reflect this
4. **Simpler validation**: One system to check instead of two

### Current State

| System | Purpose | Storage |
|--------|---------|---------|
| `Modifier` | Targeted stat changes, status tags | `state.active_modifiers: List[Modifier]` |
| `ActiveEffect` | Spatial/zonal effects | `state.active_effects: List[ActiveEffect]` |

### Target State

| System | Purpose | Storage |
|--------|---------|---------|
| `ActiveEffect` | ALL stat modifiers, action restrictions, spatial effects | `state.active_effects: List[ActiveEffect]` |
| `Marker` | Singleton tokens placed on heroes (venom, etc.) | `state.markers: Dict[MarkerType, Marker]` |

---

## Architecture

### 1. Marker System

#### Design Decision: Singleton Dictionary

Markers are **singleton per type** - only one Venom marker exists in the game. When placed on a new hero, it leaves the previous hero.

```
state.markers: Dict[MarkerType, Marker]
```

**Rationale**:
- Enforces singleton constraint at the data structure level
- O(1) lookup by marker type
- Clear semantics: `state.markers[MarkerType.VENOM]` returns the marker or KeyError
- Easy to check if placed: `marker.target_id is not None`

#### Marker Model

```
Marker:
    type: MarkerType           # VENOM, POISON, etc.
    target_id: Optional[str]   # Hero ID if placed, None if in supply
    value: int                 # Effect magnitude (e.g., -1 or -2)
    source_id: Optional[str]   # Hero who placed it (for cleanup on defeat)
```

#### Marker Lifecycle

1. **Setup**: All markers start in supply (`target_id = None`)
2. **Place**: `PlaceMarkerStep` sets `target_id` and `value`, creates linked `ActiveEffect`s
3. **Move**: Placing on new target auto-removes from previous (singleton enforcement)
4. **Remove**: `RemoveMarkerStep` sets `target_id = None`, removes linked effects
5. **End of Round**: All markers returned to supply
6. **Hero Defeat**: Markers on defeated hero returned to supply

#### Marker-to-Effect Mapping

Each marker type defines what effects it creates when placed:

```
VENOM marker with value=-1 creates:
  - ActiveEffect(AREA_STAT_MODIFIER, ATTACK, -1, POINT on target)
  - ActiveEffect(AREA_STAT_MODIFIER, DEFENSE, -1, POINT on target)
  - ActiveEffect(AREA_STAT_MODIFIER, INITIATIVE, -1, POINT on target)
```

Effects linked to markers have `marker_type` field for cleanup.

### 2. ActiveEffect Extensions

#### New Fields on ActiveEffect

```
marker_type: Optional[MarkerType]  # If created by a marker
```

#### AREA_STAT_MODIFIER Integration

`stats.py:get_computed_stat()` must query `ActiveEffect`s:

```
For each effect where:
  - effect_type == AREA_STAT_MODIFIER
  - effect.stat_type matches requested stat
  - effect is active (duration + is_active check)
  - target unit is in scope (POINT, RADIUS, etc.)
  
Sum effect.stat_value into total
```

#### Action Restrictions via ActiveEffect

Replace `status_tag="PREVENT_MOVEMENT"` with:

```
ActiveEffect(
    effect_type=TARGET_PREVENTION,  # or new ACTION_RESTRICTION type
    scope=EffectScope(shape=POINT, origin_id=target_id),
    restrictions=[ActionType.MOVEMENT],
)
```

`ValidationService.can_perform_action()` already checks `effect.restrictions` - just ensure POINT scope works.

### 3. Step Changes

#### Remove
- `CreateModifierStep` - replaced by `CreateEffectStep`

#### Add
- `PlaceMarkerStep(marker_type, target_key, value)`
- `RemoveMarkerStep(marker_type)`

#### Modify
- `CreateEffectStep` - ensure it supports all modifier use cases

### 4. Cleanup Changes

#### EffectManager

- Remove all `active_modifiers` operations
- Add `remove_effects_by_marker(state, marker_type)`
- Add `return_all_markers(state)` for end of round
- Add `return_marker(state, marker_type)` for individual removal

#### End of Round

```
1. EffectManager.expire_effects(state, THIS_ROUND)
2. EffectManager.return_all_markers(state)  # NEW
3. EffectManager.cleanup_stale_effects(state)
```

#### Hero Defeat

```
1. EffectManager.expire_by_source(state, hero_id)
2. Return any markers where marker.target_id == hero_id  # NEW
3. Return any markers where marker.source_id == hero_id  # NEW
```

---

## Migration Strategy: Clean Cut

### Approach

1. Build the new system completely
2. Migrate all usages in one pass
3. Delete the old system
4. Run full test suite to verify

No backwards compatibility period - the systems don't coexist.

### Order of Operations

1. **Add** new Marker model and storage
2. **Add** marker_type field to ActiveEffect
3. **Extend** stats.py to read from ActiveEffects
4. **Extend** ValidationService for POINT-scoped action restrictions
5. **Add** PlaceMarkerStep, RemoveMarkerStep
6. **Migrate** all CreateModifierStep usages to CreateEffectStep or PlaceMarkerStep
7. **Update** all tests
8. **Delete** Modifier model, active_modifiers, CreateModifierStep, has_status()

---

## Affected Files

### Models
- `src/goa2/domain/models/marker.py` - NEW
- `src/goa2/domain/models/effect.py` - Add marker_type field
- `src/goa2/domain/models/modifier.py` - DELETE
- `src/goa2/domain/models/__init__.py` - Update exports
- `src/goa2/domain/state.py` - Add markers dict, remove active_modifiers

### Engine
- `src/goa2/engine/stats.py` - Query ActiveEffects for stat mods
- `src/goa2/engine/validation.py` - Remove modifier checks, ensure effect checks work for POINT
- `src/goa2/engine/effect_manager.py` - Remove modifier methods, add marker methods
- `src/goa2/engine/steps.py` - Remove CreateModifierStep, add marker steps

### Effects
- `src/goa2/scripts/rogue_effects.py` - Migrate VenomStrike to use markers

### Tests
- All tests using CreateModifierStep or active_modifiers need updating
- New tests for marker system

---

## Implementation Status

**Date**: Implemented as part of marker system migration

### Completed

#### Phase 1: Add Marker System
- [x] Create `MarkerType` enum with `VENOM`
- [x] Create `Marker` model in `src/goa2/domain/models/marker.py`
- [x] Add `markers: Dict[MarkerType, Marker]` to `GameState`
- [x] Add `get_marker()`, `place_marker()`, `remove_marker()` helpers to GameState
- [x] Export Marker types from `models/__init__.py`
- [x] Write unit tests for Marker model and GameState integration (23 tests)

#### Phase 2: Extend ActiveEffect for Stat Modifiers
- [x] Add `marker_type: Optional[MarkerType]` field to `ActiveEffect`
- [x] Update `get_computed_stat()` to sum `AREA_STAT_MODIFIER` effects in scope
- [x] Add scope checking helpers to stats.py
- [x] Update `get_computed_stat()` to read marker stat effects directly
- [x] Write unit tests for stat computation via ActiveEffect (11 tests)

#### Phase 3: Add Marker Steps
- [x] Create `PlaceMarkerStep` in steps.py
- [x] Create `RemoveMarkerStep` in steps.py
- [x] Add marker cleanup to `EndPhaseCleanupStep` (return all markers at end of round)
- [x] Add marker cleanup to `DefeatUnitStep` (return markers from/by defeated hero)

#### Phase 4: Migrate Existing Usages
- [x] Migrate `VenomStrike` to use `PlaceMarkerStep` instead of 3x `CreateModifierStep`
- [x] Audited all `CreateModifierStep` usages - only VenomStrike was using it in production

#### Phase 5: Status Tags
- [x] Verified no production code uses `status_tag` with `CreateModifierStep`
- [x] Status tags are only used in tests for validation testing

### Deferred (Kept for Backwards Compatibility)

#### Phase 6: Delete Modifier System
**Decision**: Keep Modifier system for now. Rationale:
- Tests use Modifiers to set up validation scenarios
- ValidationService checks both Modifiers and ActiveEffects
- No production code creates Modifiers anymore
- Can be fully removed in a future cleanup when tests are migrated

### Verification
- [x] All 378 tests pass
- [x] VenomStrike works with marker system
- [x] Marker effects apply via `get_computed_stat()`
- [x] Markers returned at end of round
- [x] Markers returned on hero defeat

---

## Original Checklist (for reference)

### Phase 1: Add Marker System
- [ ] Create `MarkerType` enum with `VENOM` (add more as needed)
- [ ] Create `Marker` model in `src/goa2/domain/models/marker.py`
- [ ] Add `markers: Dict[MarkerType, Marker]` to `GameState`
- [ ] Add `get_marker()`, `place_marker()`, `remove_marker()` helpers to GameState
- [ ] Export Marker types from `models/__init__.py`
- [ ] Write unit tests for Marker model and GameState integration

### Phase 2: Extend ActiveEffect for Stat Modifiers
- [ ] Add `marker_type: Optional[MarkerType]` field to `ActiveEffect`
- [ ] Update `get_computed_stat()` to sum `AREA_STAT_MODIFIER` effects in scope
- [ ] Add `_is_unit_in_effect_scope()` helper to stats.py (reuse validation logic)
- [ ] Write unit tests for stat computation via ActiveEffect

### Phase 3: Add Marker Steps
- [ ] Create `PlaceMarkerStep` in steps.py
  - [ ] Sets marker.target_id and marker.value
  - [ ] Creates linked ActiveEffects based on marker type
  - [ ] Auto-removes from previous target if already placed
- [ ] Create `RemoveMarkerStep` in steps.py
  - [ ] Clears marker.target_id
  - [ ] Removes all effects with matching marker_type
- [ ] Add marker cleanup to `EndPhaseCleanupStep` (return all markers)
- [ ] Add marker cleanup to hero defeat logic
- [ ] Write integration tests for marker placement/removal

### Phase 4: Migrate Existing Usages
- [ ] Migrate `VenomStrike` to use `PlaceMarkerStep` instead of 3x `CreateModifierStep`
- [ ] Audit all `CreateModifierStep` usages in codebase
- [ ] For each usage, decide: ActiveEffect (POINT) or Marker
- [ ] Update all card effect implementations
- [ ] Update all test files using CreateModifierStep

### Phase 5: Migrate Status Tags to ActiveEffect Restrictions
- [ ] Ensure `ValidationService.can_perform_action()` handles POINT-scoped effects
- [ ] Replace any `status_tag="PREVENT_X"` with `CreateEffectStep(restrictions=[ActionType.X])`
- [ ] Remove `has_status()` function from stats.py
- [ ] Update tests

### Phase 6: Delete Modifier System
- [ ] Remove `Modifier` class from `models/modifier.py` (keep DurationType)
- [ ] Remove `active_modifiers` from `GameState`
- [ ] Remove `add_modifier()`, `get_modifiers_on()` from GameState
- [ ] Remove `CreateModifierStep` from steps.py
- [ ] Remove modifier-related methods from `EffectManager`
- [ ] Remove modifier checks from `ValidationService`
- [ ] Remove `has_status()` from stats.py
- [ ] Update `models/__init__.py` exports
- [ ] Delete or update `tests/domain/test_modifier.py`

### Phase 7: Final Verification
- [ ] Run full test suite: `PYTHONPATH=src uv run pytest --cov=goa2 tests/`
- [ ] Verify no references to `Modifier` class remain (except DurationType)
- [ ] Verify no references to `active_modifiers` remain
- [ ] Verify no references to `CreateModifierStep` remain
- [ ] Verify no references to `has_status()` remain
- [ ] Manual smoke test with demo script

---

## Example: Venom Strike Migration

### Before (Modifier-based)

```python
@register_effect("venom_strike")
class VenomStrikeEffect(CardEffect):
    def get_steps(self, state, hero, card):
        return [
            AttackSequenceStep(damage=damage, range_val=1),
            CreateModifierStep(target_key="victim_id", stat_type=StatType.ATTACK, value_mod=-1, duration=THIS_ROUND),
            CreateModifierStep(target_key="victim_id", stat_type=StatType.DEFENSE, value_mod=-1, duration=THIS_ROUND),
            CreateModifierStep(target_key="victim_id", stat_type=StatType.INITIATIVE, value_mod=-1, duration=THIS_ROUND),
        ]
```

### After (Marker-based)

```python
@register_effect("venom_strike")
class VenomStrikeEffect(CardEffect):
    def get_steps(self, state, hero, card):
        return [
            AttackSequenceStep(damage=damage, range_val=1),
            PlaceMarkerStep(
                marker_type=MarkerType.VENOM,
                target_key="victim_id",
                value=-1,  # This card applies -1 to all stats
            ),
        ]
```

The `PlaceMarkerStep` internally creates the three `ActiveEffect`s for ATTACK, DEFENSE, INITIATIVE.

---

## Example: Temporary Buff (Non-Marker)

### Before (Modifier-based)

```python
CreateModifierStep(
    target_id=hero.id,
    stat_type=StatType.DEFENSE,
    value_mod=+2,
    duration=DurationType.THIS_TURN,
)
```

### After (ActiveEffect with POINT)

```python
CreateEffectStep(
    effect_type=EffectType.AREA_STAT_MODIFIER,
    scope=EffectScope(shape=Shape.POINT, origin_id=hero.id),
    stat_type=StatType.DEFENSE,
    stat_value=+2,
    duration=DurationType.THIS_TURN,
)
```

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Missing a CreateModifierStep usage | Grep for "CreateModifierStep" and "active_modifiers" before deletion |
| Stats calculation breaks | Comprehensive unit tests for get_computed_stat() |
| Validation breaks | Existing validation tests should catch issues |
| Marker cleanup missed | Test end-of-round and hero-defeat scenarios explicitly |
| Performance regression (more effects to iterate) | Profile if needed; POINT scope check is O(1) |

---

## Success Criteria

1. All existing tests pass
2. No references to deleted classes/methods in codebase
3. Venom Strike works correctly with marker system
4. Stats computation correctly sums ActiveEffect modifiers
5. Action restrictions work with POINT-scoped effects
6. Markers return to supply at end of round
7. Markers return to supply when hero is defeated
