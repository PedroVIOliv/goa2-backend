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

---

## 6. Mandatory vs Optional Steps

Per GoA2 rules: *"Card text must be applied in exact order. If you cannot complete a mandatory step, stop and skip remaining steps."*

### Step Fields
```python
class GameStep:
    is_mandatory: bool = True  # Default: mandatory

class StepResult:
    abort_action: bool = False  # Set True to abort on failure
```

### Behavior
| Step Type | On Failure | Engine Action |
|-----------|------------|---------------|
| Mandatory (`is_mandatory=True`) | Returns `abort_action=True` | Clears stack to `FinalizeHeroTurnStep` |
| Optional (`is_mandatory=False`) | Returns `is_finished=True` | Continues to next step |

### Example Usage
```python
# "You may move 1 space" - optional
MoveUnitStep(unit_id=hero.id, range_val=1, is_mandatory=False)

# "Attack target" - mandatory (default)
SelectStep(target_type="UNIT", filters=[...])  # is_mandatory=True by default
```

### Implementation
When a step fails and `is_mandatory=True`:
1. Return `StepResult(is_finished=True, abort_action=True)`
2. Handler calls `_clear_to_finalize(state)`
3. All steps until `FinalizeHeroTurnStep` are popped and skipped

See [Card Effects Guidelines](docs/card_effects_guidelines.md) for detailed patterns.

---

## 7. Active Effects & Stats System

The engine uses a **Computed Stats** model rather than mutating base stats directly.

### The Modifier Model
Temporary buffs/debuffs are stored as `Modifier` objects in `state.active_modifiers`.

```python
class Modifier(BaseModel):
    id: str                      # Unique ID
    source_id: str               # ID of entity/card that created this
    target_id: BoardEntityID     # Affected Unit ID
    stat_type: Optional[StatType] = None
    value_mod: int = 0
    status_tag: Optional[str] = None # e.g., "IGNORE_OBSTACLES"
    duration: DurationType       # THIS_TURN, THIS_ROUND, PASSIVE
    created_at_turn: int
    created_at_round: int
```

### Usage
*   **Reading Stats:** NEVER read `unit.movement` directly. Use `stats.get_computed_stat(state, unit.id, StatType.MOVEMENT)`.
*   **Checking Status:** Use `stats.has_status(state, unit.id, "IGNORE_OBSTACLES")`.
*   **Writing Effects:** Use `state.add_modifier(Modifier(...))`.

---

## 8. Unique ID System

To prevent ID collisions between Units and Tokens:

1.  **Static IDs:** Heroes use fixed IDs (e.g., `hero_arien`).
2.  **Dynamic IDs:** Minions and Tokens MUST use `EntityFactory` to generate monotonic IDs (e.g., `minion_42`, `token_trap_105`).
3.  **Registration:** Always use `state.register_entity(entity)` to add objects to the game. This method enforces global uniqueness.
