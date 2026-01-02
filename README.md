# Guards of Atlantis II - Game Engine Backend

A high-fidelity, deterministic Python implementation of the game rules for **Guards of Atlantis II**. This project serves as the **authoritative backend engine**, designed to handle the complex state and logic of the game while providing a clean, structured interface for future **frontend implementations**.

## 🎯 Design Goals

1.  **Authoritative Logic:** The backend is the single source of truth for all rules and state transitions.
2.  **Frontend Facilitation:** By reifying logic into a stack of atomic steps, the backend simplifies client-side development. The client doesn't need to know the rules; it simply renders the state and responds to specific `InputRequests` sent by the engine.
3.  **Determinism:** Given the same sequence of inputs, the engine will always produce the same state, making replays and testing trivial.

## 🌟 Core Philosophy: "Logic as Data"

Unlike traditional engines that use deeply nested function calls, this engine uses a **Stack-Based Step Architecture**. Every action (playing a card, moving, attacking) is broken down into atomic `GameStep` objects pushed onto an `execution_stack`.

### Why this matters:
- **Mid-Action Interrupts:** If an attack requires a player to choose a defense card, the engine simply pauses, requests input, and resumes exactly where it left off.
- **Deep Nesting:** Reactions to reactions (e.g., a trap triggered by a defense card) are handled naturally by pushing new steps on top of the stack.
- **Stateless & Deterministic:** The entire state of a "paused" card resolution is captured in the stack, making it easy to serialize and resume on different server instances.

---

## 🏗 Architecture Overview

> **For a detailed deep-dive into the Engine Internals, Step Lifecycle, and Best Practices, see [ARCHITECTURE.md](ARCHITECTURE.md).**
> **Proposed Architecture Changes:**
> *   [Unique ID System Plan](docs/plan_unique_id_system.md)
> *   [Active Effects & Modifiers Plan](docs/plan_active_effects_system.md)

### 1. Game State (`GameState`)
The single source of truth. Contains the `board`, `teams`, `unit_locations`, and the two core processing containers:
- **`execution_stack`**: A LIFO list of `GameStep` instances currently being resolved.
- **`execution_context`**: A shared dictionary used by steps in the same chain to pass data (e.g., "Step 1" finds a target, "Step 2" deals damage to that target).

### 2. The Step Engine (`src/goa2/engine/steps.py`)
Logic is implemented in small, reusable classes:
- **`SelectTargetStep`**: Handles interaction with players.
- **`MoveUnitStep`**: Handles movement with pathfinding validation.
- **`AttackSequenceStep`**: A "Macro Step" that expands into sub-steps (Select -> Reaction -> Combat).
- **`ResolveTieBreakerStep`**: Handles initiative ties using coin flips and team choices.

### 3. Smart Grid (`src/goa2/domain/board.py`)
The board is a "Smart Grid" that ensures safety on non-uniform maps.
- **O(1) Lookups:** Boundary checks and neighbor detection are done via hash-map lookups.
- **Centralized Safety:** Logic always uses `board.get_neighbors(hex)` or `board.get_ring(hex, radius)`, which automatically filters out coordinates that don't exist on the map.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Extremely recommended)

### Setup
```bash
# Sync dependencies
uv sync
```

### Running the Engine Demo
We have a walkthrough script that demonstrates multi-player interaction and the step-stack in action:
```bash
PYTHONPATH=src uv run python -m goa2.scripts.demo_step_engine
```

### Running Tests & Coverage
```bash
PYTHONPATH=src uv run pytest --cov=goa2 tests/
```

---

## 📖 Developer Guide

### Implementing a New Card
To implement a card like *"Move 1, then Attack"*:
1. Create a `MacroStep` (or a helper function).
2. Return a list of steps in the desired order.

```python
class ChargeCardStep(GameStep):
    def resolve(self, state, context):
        steps = [
            MoveUnitStep(range_val=1),
            AttackSequenceStep(damage=3, range_val=1)
        ]
        return StepResult(is_finished=True, new_steps=steps)
```

### Adding a New Interaction (Input)
If you need a new type of player choice (e.g., "Choose a card to discard"):
1. Create a step that returns `requires_input=True`.
2. Provide the `player_id` and `input_request` data.
3. The `handler.py` loop will automatically pause and return that request to the client.

### Rule Constants & Physics
- **Movement Pathfinding:** Logic is centralized in `src/goa2/engine/rules.py`.
- **Combat Math:** Passive auras (Minion modifiers) are handled in `src/goa2/engine/stats.py`.

---

## 🗺 Roadmap & Rule Implementation

### 🏁 Win Conditions
- [x] **Lane Push:** Battle zone reaches the enemy throne.
- [x] **Last Push:** A push occurs when only one Wave Counter remains (Time Condition).
- [ ] **Life Counters:** A team's last life counter is flipped.

### ⚔️ Combat & Resolution Rules
- [x] **Initiative Sorting:** Simultaneous reveal followed by high-to-low resolution.
- [x] **Dynamic Tie-Breaking:** Handle cross-team coin flips and same-team choices mid-resolution.
- [x] **Death Penalty:** If a hero is defeated, team loses life counters. Correct Gold rewards awarded.
- [x] **Minion Auras:** Passive +1/-1 modifiers based on proximity (Integrated in Combat).

### 🌊 End Phase (Round Cleanup)
- [x] **Minion Battle:** Compare counts in Battle Zone. Loser removes `Difference` minions.
- [x] **Heavy Constraint:** Heavy minions **must** be the last minions removed during Minion Battle.
- [ ] **Upgrading:** Mandatory level-up and card-to-item "tucking" logic.

### 🛠 Completed Primitives (Steps)
- [x] **Push(X):** Vector-based movement with obstacle collision.
- [x] **Swap / Place:** Teleportation and position exchange.
- [x] **Respawn:** Returning defeated heroes to base and spawning new minions waves.
- [x] **Card Choice:** Players choose between Primary Action (Scripted) or Secondary Action.

---

## 📂 Project Structure

```
src/goa2/
├── domain/         # Data Models (Pydantic V2)
│   ├── models/     # Cards, Units, Teams, SpawnPoints, Modifiers
│   ├── hex.py      # Cube coordinate math
│   ├── state.py    # The GameState container
│   ├── board.py    # Grid & Zone logic
│   └── factory.py  # Entity Creation (Unique IDs)
├── engine/         # Logic Core
│   ├── steps.py    # Atomic GameStep definitions
│   ├── handler.py  # The Stack processing loop
│   ├── phases.py   # Turn/Phase orchestration
│   ├── rules.py    # Physics (Pathfinding, LOS)
│   ├── stats.py    # Aura & Modifier calculations
│   └── effects.py  # Card Logic Registry
└── data/           # Static data (Hero definitions, Map JSONs)
```