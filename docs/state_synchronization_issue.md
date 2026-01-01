# State Synchronization Issue: unit_locations vs. Board.tiles [RESOLVED]

## Status: Resolved
**Date:** 2025-01-31
**Solution:** Unified Entity Manager & Auto-Sync

## The Problem (Historical Context)
The game maintained unit positions in two separate structures:
1.  `GameState.unit_locations`
2.  `GameState.board.tiles[].occupant_id`

These often drifted out of sync during testing and initialization.

## The Solution
We implemented a **Unified Entity Manager** in `GameState`.

### 1. Single Source of Truth
*   `GameState.entity_locations` (formerly `unit_locations`) is the **Master Record**.
*   `GameState.board.tiles` is a **Read-Only Cache**.

### 2. Synchronization Validator
A Pydantic `@model_validator(mode='after')` was added to `GameState`.
*   **On Load/Init:** It wipes all tile occupancy and rebuilds it strictly from `entity_locations`.
*   **Guarantee:** It is now impossible to load a state where the board disagrees with the entity list.

### 3. Unified API
Direct dictionary access is replaced by atomic methods:
*   `state.place_entity(id, hex)`: Updates location and tile cache.
*   `state.remove_entity(id)`: Clears location and tile cache.
*   `state.move_entity(id, hex)`: Wrapper for placement.

### 4. Serialization Support
The `Hex` class was updated with a `PlainSerializer` and `BeforeValidator` to correctly handle `Hex` objects as dictionary keys in JSON (converting to/from string `"q,r,s"` representation). This ensures robust save/load cycles.

## Usage Guide
*   **Do:** Use `state.place_entity("unit_id", hex)` to put things on the board.
*   **Do:** Use `state.get_entity("id")` to find Units OR Tokens.
*   **Don't:** Manually set `tile.occupant_id`. It will be overwritten or ignored.