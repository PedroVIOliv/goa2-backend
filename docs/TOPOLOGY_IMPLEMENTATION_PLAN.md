# Topology Service Implementation Plan

## Overview

This document outlines the implementation plan for the **TopologyService** - a game-aware distance and connectivity layer that enables Nebkher's "Crack in Reality" mechanic (and future topology-altering effects).

### The Problem

Nebkher's cards split the board into disconnected regions where units "cannot interact with objects and spaces on the other side of the line, as if they did not exist."

Current architecture uses `Hex.distance()` (pure geometry) throughout the codebase. We need a topology-aware layer that:
1. Checks active `TopologyConstraint` effects
2. Returns `Infinity` for hexes in disconnected components
3. Falls back to `Hex.distance()` when no constraints apply

---

## Architecture Decision

### What Continues Using `Hex` Methods (Pure Geometry)

These operations are purely mathematical and remain unchanged:

| Method | Usage | Reason |
|--------|-------|--------|
| `Hex.neighbors()` | Raw adjacency list | Topology layer filters the results |
| `Hex.ring()` | Shape calculation | Not range checking |
| `Hex.is_straight_line()` | Geometric alignment | Unaffected by "reality" |
| `Hex.line_to()` | Path tracing for pushes | Topology checks the result |
| `Hex.direction_to()` | Directional math | Pure geometry |
| `Hex.is_on_segment()` | LOS blocking geometry | Blocker position already validated |

### What Migrates to `TopologyService` (Game Logic)

| Current | Location | Replacement |
|---------|----------|-------------|
| `origin.distance(hex)` | `validation.py`, `stats.py`, `steps.py` | `topology.distance(origin, hex, state)` |
| `s_loc.distance(t_loc)` | `rules.validate_target()` | `topology.distance(s, t, state)` |
| `origin_hex.distance(target_hex)` | `RangeFilter` | `topology.distance(o, t, state)` |
| `cand_hex.distance(target_hex) == 1` | `AdjacencyToContextFilter` | `topology.are_adjacent(a, b, state)` |
| `board.get_neighbors()` | `rules.validate_movement_path()` | `topology.get_traversable_neighbors(hex, unit, state)` |
| `cand_hex.neighbors()` | `AdjacencyFilter`, `HasEmptyNeighborFilter` | `topology.get_connected_neighbors(hex, state)` |

---

## Complete Callsite Audit

### `.distance()` Usages

#### TOPOLOGY-AWARE (14 usages - must migrate)

| File | Line | Code | Purpose |
|------|------|------|---------|
| `rules.py` | 127 | `s_loc.distance(t_loc)` | Target range validation |
| `rules.py` | 169 | `attacker_pos.distance(target_pos)` | Attack range fallback |
| `filters.py` | 111 | `origin_hex.distance(target_hex)` | RangeFilter selection |
| `filters.py` | 398 | `cand_hex.distance(target_hex) == 1` | AdjacencyToContextFilter |
| `filters.py` | 599 | `target_hex.distance(cand_hex)` | LineBehindTargetFilter |
| `steps.py` | 2701 | `loc_a.distance(loc_b)` | CheckAdjacencyStep |
| `steps.py` | 3353 | `origin.distance(hex) == 1` | CancelEffectsStep (ADJACENT) |
| `steps.py` | 3355 | `origin.distance(hex) <= range` | CancelEffectsStep (RADIUS) |
| `steps.py` | 3361 | `origin.distance(hex) <= range` | CancelEffectsStep (LINE) |
| `validation.py` | 452 | `origin.distance(hex) == 1` | _hex_in_scope (ADJACENT) |
| `validation.py` | 455 | `origin.distance(hex) <= range` | _hex_in_scope (RADIUS) |
| `validation.py` | 461 | `origin.distance(hex) <= range` | _hex_in_scope (LINE) |
| `stats.py` | 76 | `origin.distance(hex) == 1` | _hex_in_scope (ADJACENT) |
| `stats.py` | 79 | `origin.distance(hex) <= range` | _hex_in_scope (RADIUS) |

#### PURE GEOMETRY (3 usages - keep as-is)

| File | Line | Code | Purpose |
|------|------|------|---------|
| `hex.py` | 170-172 | `start.distance(end)` | `is_on_segment` triangle inequality |
| `hex.py` | 193 | `self.distance(other)` | `line_to` iteration count |
| `stats.py` | 84 | `origin.distance(hex)` | LINE shape (combined with is_straight_line) |

### `.neighbors()` / `get_neighbors()` Usages

#### TOPOLOGY-AWARE (5 usages - must migrate)

| File | Line | Code | Purpose |
|------|------|------|---------|
| `filters.py` | 204 | `cand_hex.neighbors()` | AdjacencyFilter - adjacent to tagged unit |
| `filters.py` | 348 | `cand_hex.neighbors()` | AdjacentSpawnPointFilter |
| `filters.py` | 445 | `cand_hex.neighbors()` | HasEmptyNeighborFilter (escape routes) |
| `rules.py` | 48 | `board.get_neighbors(current)` | BFS movement pathfinding |
| `map_logic.py` | 139 | `current.neighbors()` | BFS displacement pathfinding |

#### PURE GEOMETRY (3 usages - keep as-is)

| File | Line | Code | Purpose |
|------|------|------|---------|
| `board.py` | 93-95 | `h.neighbors()` | Wrapper definition (delegates) |
| `map_loader.py` | 111 | `board.get_neighbors(h)` | Static zone adjacency graph (load time) |
| `hex.py` | 148 | `hex_cursor.neighbor(i)` | Internal: `ring()` implementation |

### Other Hex Methods (All PURE GEOMETRY - keep as-is)

| Method | Usages | Reason |
|--------|--------|--------|
| `.ring()` | 2 | Shape calculation, not range checking |
| `.is_straight_line()` | 8 | Geometric alignment check |
| `.line_to()` | 0 production | Tests only |
| `.direction_to()` | 3 | Directional math for pushes |
| `.neighbor()` | 2 | Single neighbor in direction (caller validates) |
| `.is_on_segment()` | 1 | LOS geometry |

### Code Duplication to Consolidate

There are **3 nearly-identical implementations** of `_hex_in_scope`:
- `validation.py:435-471`
- `stats.py:61-100`
- `steps.py:3342-3369` (in CancelEffectsStep)

These will be consolidated into `TopologyService.hex_in_scope()`.

---

## Implementation Phases

### Phase 1: Foundation (New Files & Models)

#### 1.1 Add New `EffectType` Values

**File:** `src/goa2/domain/models/effect.py`

```python
class EffectType(str, Enum):
    # ... existing ...
    TOPOLOGY_SPLIT = "TOPOLOGY_SPLIT"          # Tier 2: Crack in Reality
    TOPOLOGY_ISOLATION = "TOPOLOGY_ISOLATION"  # Tier 3: Shift Reality
```

#### 1.2 Extend `ActiveEffect` Schema

**File:** `src/goa2/domain/models/effect.py`

Add optional fields for topology data:
```python
class ActiveEffect(BaseModel):
    # ... existing fields ...
    
    # Topology constraint fields (for TOPOLOGY_SPLIT / TOPOLOGY_ISOLATION)
    split_axis: Optional[str] = None       # "q", "r", or "s"
    split_value: int = 0                   # The coordinate value of the line
    isolated_hex: Optional[Hex] = None     # For Tier 3 - Nebkher's specific position
```

#### 1.3 Create `engine/topology.py`

**New file:** `src/goa2/engine/topology.py`

```python
"""
TopologyService: Dynamic board connectivity aware of reality splits.

This service wraps all distance/connectivity queries to respect active
TopologyConstraint effects (Nebkher's Crack in Reality, etc.).

Usage:
    from goa2.engine.topology import TopologyService
    
    topo = TopologyService()
    if topo.distance(origin, target, state) <= range:
        # Target is in range (and connected)
"""

from __future__ import annotations
import math
from typing import List, Optional, TYPE_CHECKING

from goa2.domain.hex import Hex
from goa2.domain.models.effect import ActiveEffect, EffectType, Shape, DurationType
from goa2.domain.types import BoardEntityID

if TYPE_CHECKING:
    from goa2.domain.state import GameState


class TopologyService:
    """Topology-aware distance and connectivity service."""

    # --- Primary API ---

    def distance(self, origin: Hex, target: Hex, state: "GameState") -> int | float:
        """
        Returns topology-aware distance.
        Returns math.inf if hexes are in disconnected components.
        Falls back to Hex.distance() when no constraints apply.
        """
        if not self.are_connected(origin, target, state):
            return math.inf
        return origin.distance(target)

    def are_connected(self, origin: Hex, target: Hex, state: "GameState") -> bool:
        """Check if hexes can interact given active topology constraints."""
        for effect in state.active_effects:
            if effect.effect_type == EffectType.TOPOLOGY_SPLIT:
                if not self._check_split(origin, target, effect):
                    return False
            elif effect.effect_type == EffectType.TOPOLOGY_ISOLATION:
                if not self._check_isolation(origin, target, effect):
                    return False
        return True

    def are_adjacent(self, a: Hex, b: Hex, state: "GameState") -> bool:
        """Game-aware adjacency: geometric adjacency + connectivity."""
        if a.distance(b) != 1:
            return False
        return self.are_connected(a, b, state)

    def get_connected_neighbors(self, hex: Hex, state: "GameState") -> List[Hex]:
        """Returns geometric neighbors that are connected (not split off)."""
        return [n for n in hex.neighbors() if self.are_connected(hex, n, state)]

    def get_traversable_neighbors(
        self, hex: Hex, unit_id: str, state: "GameState"
    ) -> List[Hex]:
        """
        Returns neighbors that a unit can actually move to.
        Combines: topology + on-map + not-obstacle checks.
        """
        result = []
        for n in hex.neighbors():
            # Must be connected (topology)
            if not self.are_connected(hex, n, state):
                continue
            # Must be on map
            if not state.board.is_on_map(n):
                continue
            # Must not be obstacle
            tile = state.board.get_tile(n)
            if tile and tile.is_obstacle:
                continue
            result.append(n)
        return result

    def hex_in_scope(
        self,
        origin: Hex,
        target: Hex,
        scope_shape: Shape,
        scope_range: int,
        state: "GameState",
    ) -> bool:
        """
        Consolidated scope check (replaces 3 duplicate implementations).
        Returns True if target is within scope of origin, respecting topology.
        """
        if scope_shape == Shape.GLOBAL:
            # "Global" means "everywhere connected to source"
            return self.are_connected(origin, target, state)

        if scope_shape == Shape.POINT:
            return origin == target

        if scope_shape == Shape.ADJACENT:
            return self.are_adjacent(origin, target, state)

        if scope_shape == Shape.RADIUS:
            dist = self.distance(origin, target, state)
            return dist <= scope_range

        if scope_shape == Shape.LINE:
            if not origin.is_straight_line(target):
                return False
            dist = self.distance(origin, target, state)
            return dist <= scope_range

        if scope_shape == Shape.ZONE:
            # Zone checks are unaffected by topology (same zone = same zone)
            origin_zone = state.board.get_zone_for_hex(origin)
            target_zone = state.board.get_zone_for_hex(target)
            return origin_zone == target_zone and origin_zone is not None

        return False

    # --- Internal Helpers ---

    def _get_region(self, hex: Hex, effect: ActiveEffect) -> str:
        """Returns 'NEGATIVE', 'ZERO', or 'POSITIVE' based on split axis."""
        axis = effect.split_axis
        if not axis:
            return "ZERO"
        value = getattr(hex, axis)
        split_value = effect.split_value

        if value < split_value:
            return "NEGATIVE"
        elif value > split_value:
            return "POSITIVE"
        else:
            return "ZERO"

    def _check_split(self, origin: Hex, target: Hex, effect: ActiveEffect) -> bool:
        """
        Tier 2 (Crack in Reality): NEGATIVE ↔ POSITIVE blocked, ZERO is bridge.
        Returns True if connected, False if blocked.
        """
        origin_region = self._get_region(origin, effect)
        target_region = self._get_region(target, effect)

        # Block NEGATIVE ↔ POSITIVE direct interaction
        if origin_region == "POSITIVE" and target_region == "NEGATIVE":
            return False
        if origin_region == "NEGATIVE" and target_region == "POSITIVE":
            return False

        return True

    def _check_isolation(self, origin: Hex, target: Hex, effect: ActiveEffect) -> bool:
        """
        Tier 3 (Shift Reality): Same as split + isolated_hex only reachable from ZERO.
        """
        # First apply split rules
        if not self._check_split(origin, target, effect):
            return False

        # Then check isolation of Nebkher's hex
        if effect.isolated_hex and target == effect.isolated_hex:
            origin_region = self._get_region(origin, effect)
            if origin_region != "ZERO":
                return False

        return True


# Singleton instance for convenience
_topology_service: Optional[TopologyService] = None


def get_topology_service() -> TopologyService:
    """Get the global TopologyService instance."""
    global _topology_service
    if _topology_service is None:
        _topology_service = TopologyService()
    return _topology_service
```

---

### Phase 2: Migration (19 Callsites)

#### 2.1 `engine/rules.py` (3 changes)

| Line | Current | New |
|------|---------|-----|
| 48 | `board.get_neighbors(current)` | `topology.get_traversable_neighbors(current, unit_id, state)` |
| 127 | `s_loc.distance(t_loc)` | `topology.distance(s_loc, t_loc, state)` |
| 169 | `attacker_pos.distance(target_pos)` | `topology.distance(attacker_pos, target_pos, state)` |

**Note:** `validate_movement_path()` signature needs to accept `state` instead of just `board`.

#### 2.2 `engine/filters.py` (6 changes)

| Line | Filter | Current | New |
|------|--------|---------|-----|
| 111 | `RangeFilter` | `origin_hex.distance(target_hex)` | `topology.distance(...)` |
| 204 | `AdjacencyFilter` | `cand_hex.neighbors()` | `topology.get_connected_neighbors(...)` |
| 348 | `AdjacentSpawnPointFilter` | `cand_hex.neighbors()` | `topology.get_connected_neighbors(...)` |
| 398 | `AdjacencyToContextFilter` | `cand_hex.distance(...) == 1` | `topology.are_adjacent(...)` |
| 445 | `HasEmptyNeighborFilter` | `cand_hex.neighbors()` | `topology.get_connected_neighbors(...)` |
| 599 | `LineBehindTargetFilter` | `target_hex.distance(cand_hex)` | `topology.distance(...)` |

#### 2.3 `engine/validation.py` (Consolidate `_hex_in_scope`)

Replace `_hex_in_scope()` implementation (lines 435-471) to use `TopologyService.hex_in_scope()`.

#### 2.4 `engine/stats.py` (Consolidate `_hex_in_scope` + 1 ring check)

| Line | Current | New |
|------|---------|-----|
| 61-100 | `_hex_in_scope()` function | Use `TopologyService.hex_in_scope()` |
| 222 | `state.board.get_ring(target_loc, 1)` | Filter ring results through `topology.are_connected()` |

#### 2.5 `engine/steps.py` (2 changes)

| Line | Step | Current | New |
|------|------|---------|-----|
| 2701 | `CheckAdjacencyStep` | `loc_a.distance(loc_b) == 1` | `topology.are_adjacent(...)` |
| 3342-3369 | `CancelEffectsStep._hex_in_scope()` | Duplicate implementation | Use `TopologyService.hex_in_scope()` |

#### 2.6 `engine/map_logic.py` (1 change)

| Line | Function | Current | New |
|------|----------|---------|-----|
| 139 | `find_nearest_empty_hexes` | `current.neighbors()` | `topology.get_traversable_neighbors(...)` |

---

### Phase 3: Tests

#### 3.1 Unit Tests for `TopologyService`

**New file:** `tests/engine/test_topology.py`

Test cases:
- `test_distance_no_constraints()` - Falls back to Hex.distance
- `test_distance_with_split_same_side()` - Returns geometric distance
- `test_distance_with_split_opposite_sides()` - Returns infinity
- `test_distance_through_zero_bridge()` - Zero region connects both sides
- `test_are_adjacent_across_split()` - Returns False even if geometrically adjacent
- `test_isolation_blocks_nebkher_from_sides()` - Tier 3 specific test
- `test_isolation_allows_zero_to_nebkher()` - Tier 3 bridge works
- `test_global_scope_respects_split()` - Global ≠ entire map

#### 3.2 Integration Tests

- Test movement pathfinding fails across split
- Test attack targeting fails across split
- Test aura effects don't apply across split
- Test units on "ZERO" line can interact with both sides

---

### Phase 4: Create Nebkher Hero

Once infrastructure is complete, create:

**Files:**
- `src/goa2/data/heroes/nebkher.py` - Hero definition
- `src/goa2/scripts/nebkher_effects.py` - Card effect implementations

**Key card effects:**

```python
# Crack in Reality (Tier 2)
@register_effect("crack_in_reality")
class CrackInRealityEffect(CardEffect):
    def get_steps(self, state, hero, card) -> List[GameStep]:
        nebkher_hex = state.entity_locations.get(BoardEntityID(hero.id))
        return [
            SelectStep(
                target_type="AXIS",  # New: player picks which axis
                prompt="Choose the direction of the split",
                output_key="chosen_axis",
            ),
            CreateTopologySplitStep(  # New step type
                axis_key="chosen_axis",
                origin_hex=nebkher_hex,
                duration=DurationType.THIS_TURN,
            ),
        ]
```

---

## Files Summary

### Files to Create

| File | Purpose |
|------|---------|
| `src/goa2/engine/topology.py` | TopologyService implementation |
| `tests/engine/test_topology.py` | Unit tests for TopologyService |
| `src/goa2/data/heroes/nebkher.py` | Hero definition (Phase 4) |
| `src/goa2/scripts/nebkher_effects.py` | Card effects (Phase 4) |

### Files to Modify

| File | Changes |
|------|---------|
| `domain/models/effect.py` | Add `TOPOLOGY_SPLIT`, `TOPOLOGY_ISOLATION`, new fields |
| `engine/rules.py` | 3 callsites + signature change for `validate_movement_path` |
| `engine/filters.py` | 6 callsites |
| `engine/validation.py` | Replace `_hex_in_scope` implementation |
| `engine/stats.py` | Replace `_hex_in_scope` + 1 minion ring check |
| `engine/steps.py` | 2 callsites |
| `engine/map_logic.py` | 1 callsite |

---

## Edge Cases

### 1. "Global" Effects

Per Nebkher doc: *"Global does not mean 'entire map'. It means 'everywhere reachable by the source.'"*

Current code has `Shape.GLOBAL` that returns `True` unconditionally. The new `TopologyService.hex_in_scope()` will check connectivity for GLOBAL scope.

### 2. Game Engine vs. Unit Interaction

Per Nebkher doc: *"Minion Battle (counting minions to determine zone control) respects the split? No - the Engine counts minions; it does not require minions to 'see' each other."*

**Decision:** Minion Battle counting does NOT use TopologyService. However, minion defense modifiers (aura-style bonuses) DO respect splits.

### 3. The "Bridge" (Region Zero)

Units on the split line (`q=0`, `r=0`, or `s=0` depending on axis) can interact with both sides. This acts as a "bridge" that units can step onto from either side.

### 4. Tier 3 Isolation

Shift Reality adds: "Cannot interact **with you**" - meaning Nebkher's specific hex is only reachable from other hexes on the split line (Region Zero), not from either side directly.

---

## Estimated Effort

| Phase | Effort |
|-------|--------|
| Phase 1: Foundation | ~2 hours |
| Phase 2: Migration | ~3 hours |
| Phase 3: Tests | ~2 hours |
| Phase 4: Nebkher Hero | ~4 hours |
| **Total** | **~11 hours** |
