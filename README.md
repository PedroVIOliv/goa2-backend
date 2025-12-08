# Guards of Atlantis II - Game Engine Backend

This project is a Python implementation of the game rules and engine for **Guards of Atlantis II**, a MOBA-style board game. It is designed to be a robust, stateless-server-friendly backend that handles complex turn-based logic, interruptions, and effect resolution.

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Recommended for dependency management)

### Installation
```bash
# Install dependencies
uv sync
```

### Running Tests
We use `pytest` for testing. The suite covers unit tests, integration tests, and full character script validations.
```bash
# Run all tests
uv run pytest tests/

# Run specific character tests
uv run pytest tests/scripts/test_arien.py
```

---

## 🏗 Architecture

The engine follows a **Command-driven** and **State-centric** architecture.

### 1. Game State (`GameState`)
The `GameState` object is the single source of truth. It contains:
- **Board**: Hex grid, zones, and unit locations.
- **Teams/Units**: Mutable state of heroes and minions.
- **Stacks & Queues**:
  - `input_stack`: Push-down automaton for handling multi-step user input (e.g., Attack -> Select Target -> Defense Card).
  - `resolution_queue`: Queue of cards/actions to be resolved in the current phase.

### 2. Commands (The Action Layer)
State mutations **ONLY** happen via `Command` objects (found in `src/goa2/engine/actions.py`).
- **Pattern**: `Command.execute(state) -> GameState`
- **Atomic**: Each command performs a specific logic block.
- **Input-Driven**: Commands check the `input_stack` for required parameters. If input is missing, they raise `ValueError` (in tests) or would realistically return a request to the frontend.

**Key Commands:**
- `PlayCardCommand`: Commits a card to the resolution queue.
- `ResolveNextCommand`: Advances the game loop, popping cards and triggering actions.
- `ChooseActionCommand`: Handles the player's choice of Primary vs. Secondary action.
- `AttackCommand` / `PerformMovementCommand`: Execute specific game mechanics.

### 3. Effect System
The engine supports complex card effects via a **Hook System** (`src/goa2/engine/effects.py`).
- **Registry**: Effects are registered by string ID (e.g., `"effect_attack_discard_behind"`).
- **Hooks**:
  - `on_pre_action(ctx)`: Runs before the main action. Can interrupt flow by pushing to `input_stack`.
  - `on_post_action(ctx)`: Runs after the action completes.
- **Persistence**: Effects needing to persist state across interruptions (e.g., remembering a target while waiting for input) use `card.metadata`.

### 4. Hex Grid
The board uses **Cube Coordinates** (`q, r, s`) defined in `src/goa2/domain/hex.py`.
- `q + r + s == 0` constraint is enforced.
- Configured with Pydantic's `ConfigDict(frozen=True)` to ensure hashability for map lookups.

---

## 🧠 Coding Best Practices

### 1. State Immutability (Conceptual)
While Python objects are mutable, treat `GameState` as something that transitions from one valid state to another. Avoid modifying state deeply nested within helper functions; keep mutations inside `Command.execute`.

### 2. Input Handling
If an action requires user input (e.g., "Select a Hex"):
1. **Push Input Request**: The Command/Effect pushes an `InputRequest` to `state.input_stack`.
2. **Return**: The execution halts.
3. **Resume**: The next external call (from User/Test) provides the input via a specific Command (e.g., `ResolveSkillCommand`), which reads the top of the stack.

### 3. Pydantic V2
We use Pydantic V2.
- Use `model_config = ConfigDict(...)` instead of `class Config:`.
- Ensure models that need to be hashed (like `Hex`) are frozen.

### 4. Testing
- **Unit Tests**: Test individual components (`hex`, `card`, `combat`).
- **Script Tests** (`tests/scripts/`): These are high-value integration tests that verify specific Hero behaviors. Use `arien.py` as a template.

---

## 📂 Directory Structure

```
src/goa2/
├── domain/         # Data Models (State, Hex, Card, Unit)
│   ├── models/     # Core Entity Definitions
│   └── ...
├── engine/         # Logic Core
│   ├── actions.py  # Command implementations
│   ├── combat.py   # Math/Rules for combat
│   ├── effects.py  # Effect Registry & Base Classes
│   └── rules.py    # Static Rule Logic (LOS, Movement)
└── scripts/        # Hero-specific Logic/Effects (Arien, etc.)
```

## 🛠 Adding Content

### Adding a New Hero
1. Define the Hero's cards and stats.
2. If cards have unique logic, implement an `Effect` class in a new script (e.g., `src/goa2/scripts/new_hero.py`).
3. Register the effect in `goa2.scripts.registry` (if applicable).
4. Create a test file in `tests/scripts/test_new_hero.py` verifying the card flow.

### Adding a New Mechanic
1. Update `src/goa2/domain/models/` if new state is needed.
2. Implement the logic in `src/goa2/engine/actions.py` or `mechanics.py`.
3. Ensure `InputRequestType` is updated if new input forms are required.
