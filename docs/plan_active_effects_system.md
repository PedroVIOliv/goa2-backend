# Engineering Plan: Active Effects & Modifiers System

## 1. Problem Statement
The current engine reads stats directly from data objects (`unit.movement`, `card.attack_value`). This is insufficient for a card game where temporary status effects are core mechanics.

**Current Limitations:**
1.  **No "Buff" Storage:** If a card says "This turn, you have +1 Movement", there is nowhere to store this state.
2.  **Static Physics:** The `rules.py` module calculates movement based on the board geometry but cannot account for logic overrides like "Ignore Obstacles" or "Cannot Fast Travel".
3.  **Hardcoded Auras:** Minion defense auras are currently hardcoded in `stats.py`, making them difficult to extend or disable (e.g., "Ignore all minion defense modifiers").

## 2. Proposed Solution

### 2.1 The `Modifier` Data Structure
We will treat logic modifications as data.

```python
class Modifier(BaseModel):
    id: str                  # unique instance id
    source_id: str           # e.g., "card_deluge"
    target_id: str           # e.g., "hero_arien"
    
    # Payload
    stat_type: Optional[StatType] = None  # ATTACK, DEFENSE, MOVEMENT, RANGE
    value_mod: int = 0                    # +1, -1
    status_tag: Optional[str] = None      # "IGNORE_OBSTACLES", "SILENCED"
    
    # Lifecycle
    duration: DurationType   # THIS_TURN, THIS_ROUND, PASSIVE
    created_at_turn: int
    created_at_round: int
```

### 2.2 State Integration
*   **Container:** `GameState.active_modifiers: List[Modifier]`.
*   **Querying:** A linear scan of this list is sufficient for the scale of a board game (< 100 active modifiers).

### 2.3 The "Computed Stats" Layer (`stats.py`)
We will refactor `goa2.engine.stats` to be the single source of truth for numeric values, replacing direct attribute access.

*   **Logic:** `Computed Value = Base Value + Item Bonuses + Sum(Active Modifiers)`
*   **New API:**
    *   `stats.get_movement(state, unit) -> int`
    *   `stats.get_attack_power(state, attacker, card) -> int`
    *   `stats.has_status(state, unit, tag) -> bool`

### 2.4 Physics Integration (`rules.py`)
Update `rules.validate_movement_path` and similar functions to check status tags via `stats.py`.

*   *Before:* `if tile.is_obstacle:`
*   *After:* `if tile.is_obstacle and not stats.has_status(state, unit, "IGNORE_OBSTACLES"):`

### 2.5 Lifecycle Management
Implement cleanup logic in `phases.py`:
*   **End of Turn:** Remove modifiers where `duration == THIS_TURN`.
*   **End of Round:** Remove modifiers where `duration == THIS_ROUND`.

## 3. Success Criteria
1.  **Temporal Correctness:** A "This Turn" buff automatically expires when the turn changes.
2.  **Stacking Rules:** Multiple `+1` modifiers correctly sum up to `+2`.
3.  **Negative/Clamping:** Modifiers can reduce stats, but logic ensures values don't break (e.g., Movement < 0 clamps to 0).
4.  **Tag Support:** A unit with the "IGNORE_OBSTACLES" tag can validly move through a Wall in the pathfinding algorithm.
