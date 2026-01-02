# Engineering Plan: Global Unique ID System

## 1. Problem Statement
The current engine relies on `UnitID` and `BoardEntityID` being simple strings. While `Unit` inherits from `BoardEntity`, they are stored in separate containers (`teams` for Units, `misc_entities` for Tokens) within the `GameState`.

**Risks:**
1.  **ID Collision:** There is no mechanism preventing a Token from being created with the ID `"skeleton_1"`, which might already belong to a Minion.
2.  **Ambiguous Retrieval:** `state.get_entity(id)` checks `misc_entities` first, then `teams`. A collision results in the wrong object being returned, potentially causing crashes or subtle logic bugs (e.g., applying damage to a Token instead of a Minion).
3.  **Manual Management:** Spawning logic currently requires manually assigning IDs, which is error-prone.

## 2. Proposed Solution

### 2.1 Monotonic Sequence Generator
We will move away from manual ID naming for dynamic entities.
*   **Add to GameState:** `next_entity_id: int = 1`
*   **Behavior:** This counter increments every time a dynamic entity (Minion, Token) is created. It is never reset during a game, ensuring historical uniqueness even if entities are removed.

### 2.2 ID Formatting Standard
*   **Static Entities (Heroes):** Retain human-readable, deterministic IDs defined in data files (e.g., `hero_arien`, `hero_knight`).
*   **Dynamic Entities (Minions/Tokens):** Use a strict format: `{type}_{sequence_number}`.
    *   Example: `minion_42`, `token_trap_43`, `token_objective_44`.

### 2.3 Centralized Registration (The "Safety Valve")
We will implement a `register_entity` method in `GameState` that acts as the **only** write-path for adding entities to the board/roster.

```python
def register_entity(self, entity: BoardEntity, collection_type: str):
    # 1. Check Global Uniqueness
    if self.get_entity(entity.id) is not None:
        raise ValueError(f"ID Collision: {entity.id} already exists!")
    
    # 2. Add to specific container
    if collection_type == "token":
        self.misc_entities[entity.id] = entity
    elif collection_type == "minion":
        # Add to specific team list
        pass
```

### 2.4 Entity Factory
A helper class `EntityFactory` will wrap the generation logic:
```python
class EntityFactory:
    @staticmethod
    def create_minion(state: GameState, team: TeamColor, m_type: MinionType) -> Minion:
        uid = f"minion_{state.next_entity_id}"
        state.next_entity_id += 1
        return Minion(id=uid, ...)
```

## 3. Success Criteria
1.  **Uniqueness Guaranteed:** Attempting to manually insert a duplicate ID raises a strict `ValueError`.
2.  **Safe Retrieval:** `state.get_entity(id)` is guaranteed to return the correct object because overlap is impossible.
3.  **Persistence:** The `next_entity_id` counter is saved/loaded with `GameState`, ensuring uniqueness persists across save games.
4.  **Refactor:** All `new Minion(...)` calls in the codebase are replaced by `EntityFactory` calls.
