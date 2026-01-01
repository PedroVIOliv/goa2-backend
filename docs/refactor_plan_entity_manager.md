# Refactor Plan: Unified Entity Manager & State Synchronization

## 1. Problem Statement
The current engine suffers from a **"Double Source of Truth"** issue regarding object positions:
1.  `GameState.unit_locations`: A dictionary mapping `UnitID -> Hex`.
2.  `Board.tiles[hex].occupant_id`: A field on the Tile object.

These two sources can drift out of sync, particularly during:
*   **Initialization/Loading:** Loading a JSON state might populate one but not the other.
*   **Testing:** Developers manually setting `tile.occupant_id` to "hack" a scenario without updating `unit_locations`.
*   **Non-Unit Entities:** Tokens (Traps, Totems) currently have no registry in `GameState`, making them difficult to track consistently.

## 2. The Solution: Unified Entity Manager
We will transform `GameState` into the authoritative **Entity Manager**.

### Core Principles
1.  **Single Source of Truth:** `entity_locations` (formerly `unit_locations`) is the Master Record.
2.  **Cached View:** `board.tiles[].occupant_id` is a *read-only cache*, automatically synchronized with the Master Record.
3.  **Unified API:** Direct dictionary access is forbidden. All position changes must go through `state.place_entity()` / `state.remove_entity()`.
4.  **Generic Storage:** A new `misc_entities` registry will hold non-Unit objects (Tokens), putting them on equal footing with Units.

---

## 3. Implementation Steps

### Step 1: GameState Schema Updates (`src/goa2/domain/state.py`)
*   **Rename:** `unit_locations` $\to$ `entity_locations` (Dict[BoardEntityID, Hex]).
*   **Add:** `misc_entities` (Dict[BoardEntityID, Any]) to store Tokens/Objects not belonging to a Team.
*   **Validator:** Implement `rebuild_occupancy_cache` (@model_validator) to automatically populate `board.tiles` from `entity_locations` on load.

### Step 2: Unified API Implementation (`src/goa2/domain/state.py`)
Implement the following "Primitive" methods. Game steps should uses these exclusively.

*   `place_entity(id, hex)`:
    *   Updates `entity_locations`.
    *   Updates `board.tiles[hex].occupant_id`.
    *   Handles overwriting/clearing previous locations automatically.
*   `remove_entity(id)`:
    *   Removes from `entity_locations`.
    *   Clears `board.tiles[hex].occupant_id`.
*   `get_entity(id)`:
    *   Checks `misc_entities` first.
    *   Then checks `teams` (Heroes/Minions).
*   **Backwards Compatibility Wrappers:**
    *   `move_unit(id, hex)` -> calls `place_entity`.
    *   `remove_unit(id)` -> calls `remove_entity`.

### Step 3: Engine Logic Updates
Review and update core engine modules to rely on `entity_locations` or the new API:
*   `goa2/engine/rules.py` (Pathfinding): Ensure it checks `state.is_occupied(hex)` or `state.get_entity_at(hex)`.
*   `goa2/engine/filters.py`: Update `OccupiedFilter` to use the unified system.
*   `goa2/engine/steps.py`:
    *   `MoveUnitStep`: Logic remains valid (calls `move_unit`), but underlying storage changes.
    *   `SwapUnitsStep`: Ensure it uses `place_entity` for the swap to guarantee cache updates.

### Step 4: Test Suite Refactor (The "Great Cleanup")
**Critical:** We must eradicate the pattern of manually setting tile occupancy in tests.

**Bad Pattern (To Remove):**
```python
state.board.get_tile(hex).occupant_id = "some_id"  # DANGEROUS!
```

**New Pattern:**
```python
state.place_entity("some_id", hex)  # SAFE
```

We will need to grep for `.occupant_id =` in `tests/` and systematically replace them.

---

## 4. Impact Analysis

### On Moving (`MoveUnitStep`)
*   **Status:** Safe.
*   **Change:** `MoveUnitStep` calls `state.move_unit`. This wrapper will now call `place_entity`, ensuring that moving a unit updates both the Dictionary and the Tile Cache atomically.

### On Spawning / Placing (`PlaceUnitStep`, `RespawnHeroStep`)
*   **Status:** Safe.
*   **Change:** Similar to moving. `PlaceUnitStep` will use the authoritative API. Because the Validator exists, if we load a game where a hero was "Mid-Spawn", the board tiles will correctly reflect their position immediately.

### On Swapping (`SwapUnitsStep`)
*   **Status:** Safe.
*   **Change:** `SwapUnitsStep` logic (`loc_a = locations[a]`, `move_unit(a, loc_b)`) works perfectly with the new system. The atomic `place_entity` ensures no "ghost" copies are left behind during the swap.

### On Tokens & Obstacles
*   **Status:** **Major Improvement.**
*   **Change:** Previously, Tokens were just "IDs on tiles". Now, they are first-class citizens.
    *   We can look up a Trap by ID: `state.get_entity("trap_1")`.
    *   We can find where a specific Totem is: `state.entity_locations["totem_red"]`.
    *   We can apply "Push" logic to Tokens if game rules allow, because they have a recorded location.

## 5. Summary of Benefits
1.  **Zero Desync:** It becomes impossible for the Map and the Entity List to disagree.
2.  **Simplified Tests:** No more 3-line setups to hack a unit onto the board. Just `state.place_entity()`.
3.  **Future Proofing:** Ready for "Neutral Monsters", "Movable Terrain", or "Complex Traps" via `misc_entities`.
