# Guards of Atlantis II - Engine Architecture Guide

This document documents the internal architecture of the backend engine. It is intended for developers implementing new steps, cards, or game mechanics.

## 1. The Stack-Based Engine (`handler.py`)

The core of the engine is a **Last-In, First-Out (LIFO)** execution stack (`state.execution_stack`).

### The Resolution Loop
The `process_resolution_stack` function follows this strict cycle:

1.  **POP:** The top step is removed from the stack *before* execution.
2.  **RESOLVE:** The step's `resolve(state, context)` method is called.
3.  **HANDLE RESULT:**
    *   **Input Needed:** If `result.requires_input` is True, the step is pushed **back** onto the stack, and the loop pauses to wait for the client.
    *   **Not Finished:** If `result.is_finished` is False, the step is pushed **back** onto the stack.
    *   **Finished:** The step remains popped (discarded).
4.  **SPAWN NEW STEPS:** If `result.new_steps` is returned, they are added to the stack.

### ⚠️ Critical Rule: Stack Manipulation
**NEVER** modify `state.execution_stack` directly inside a Step's `resolve` method if you can avoid it.
*   **Bad:** Calling `push_steps(...)` inside `resolve`. This appends to the stack *above* the current step's intended successors, potentially causing order of execution bugs or infinite loops if the current step isn't popped correctly.
*   **Good:** Returning a list of `GameStep` objects in `StepResult(new_steps=[...])`. The handler ensures these are pushed in the correct order (Reversed, so the first item in the list becomes the new Top of Stack).

---

## 2. The Step Lifecycle

A `GameStep` is an atomic unit of logic.

### Anatomy
```python
class MyStep(GameStep):
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        # 1. Read State
        # 2. Perform Logic (Modify State)
        # 3. Return Result
        return StepResult(is_finished=True, new_steps=[NextStep()])
```

### Context Passing
*   `execution_context`: A shared dictionary that persists across the current resolution chain.
*   **Use Case:** Passing a "Selected Target ID" from a `SelectStep` to a `ResolveCombatStep`.
*   **Cleanup:** `FinalizeHeroTurnStep` clears the context after a player's turn to prevent data pollution between turns.

---

## 3. The Turn Cycle (Round Logic)

The game does not use a `for player in players:` loop. Instead, it uses a **Dynamic Recursion** loop via steps.

### The Cycle
1.  **`FindNextActorStep`**: Calls `phases.resolve_next_action(state)`.
2.  **`phases.py` Logic**:
    *   Sorts `unresolved_hero_ids` by Initiative.
    *   If **Tie**: Pushes `ResolveTieBreakerStep`.
    *   If **Winner**: Pushes `[ResolveCardStep(Winner), FinalizeHeroTurnStep(Winner)]`.
    *   If **Empty**: Calls `end_turn(state)`.
3.  **`ResolveCardStep`**: Pauses for Player Input (Primary vs Secondary Action). Spawns the action steps (e.g., `AttackSequenceStep`).
4.  **Action Execution**: The spawned steps run (Move, Attack, etc.).
5.  **`FinalizeHeroTurnStep`**:
    *   Moves card from `current_turn_card` to `played_cards` (Resolved).
    *   Clears `execution_context`.
    *   **Crucial:** Spawns `FindNextActorStep` to restart the cycle.

### Diagram
```text
Start -> FindNext -> [Wait for Input] -> ResolveCard -> [Action Steps] -> Finalize -> FindNext ...
           ^                                                                            |
           |____________________________________________________________________________|
```

---

## 4. Entity Lifecycle & "Gotchas"

### Hero Cards
1.  **Planning:** Card moves from `Hand` -> `pending_inputs` buffer.
2.  **Revelation:** Card moves from `buffer` -> `hero.current_turn_card`.
3.  **Resolution:** `ResolveCardStep` reads `hero.current_turn_card`.
4.  **Finalization:** `hero.resolve_current_card()` moves it to `hero.played_cards`.
5.  **End Phase:** `hero.retrieve_cards()` moves it back to `Hand`.

**Bug Risk:** If you try to access `hero.current_turn_card` *after* `FinalizeHeroTurnStep` has run, it will be `None`. Steps that depend on the card must run *before* Finalization.

### Minion Death
1.  **Defeat (`DefeatUnitStep`):**
    *   Calculates Rewards (Gold, Life Counters).
    *   Spawns `RemoveUnitStep`.
2.  **Removal (`RemoveUnitStep`):**
    *   Purely removes unit from Board and Location map.
    *   Does NOT trigger rewards (used for "Remove" effects).

---

## 5. Development Patterns

### Pure Functions vs Steps
*   **Logic** (Math, Geometry, Triggers) should go in `rules.py`, `stats.py`, or `map_logic.py`. These functions should return values, not modify state if possible.
*   **Steps** (`steps.py`) should call these functions and apply the changes to the `GameState`.

### Testing
*   **Unit Tests:** Test pure functions directly.
*   **Integration Tests:** Test Steps by setting up a `GameState`, pushing the Step, and calling `process_resolution_stack(state)`.
*   **Verification:** Assert `state` changes (positions, gold, counters) after the stack is empty.
