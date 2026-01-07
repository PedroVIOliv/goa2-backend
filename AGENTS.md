# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Guards of Atlantis II (GoA2) backend - a deterministic, stack-based game engine for a hexagonal tactical game. Built with Python 3.11+ and Pydantic V2.

**Core Philosophy:** "Logic as Data" - uses atomic game steps pushed onto a LIFO execution stack instead of nested function calls, enabling pauseable mid-action gameplay with input requests.

## Development Commands

```bash
# Install dependencies
uv sync

# Run all tests with coverage
PYTHONPATH=src uv run pytest --cov=goa2 tests/

# Run single test file
PYTHONPATH=src uv run pytest tests/engine/test_steps.py

# Run single test function
PYTHONPATH=src uv run pytest tests/engine/test_steps.py::test_function_name -v

# Interactive demo
PYTHONPATH=src uv run python -m goa2.scripts.demo_step_engine

# Code quality
uv run ruff check src/
uv run black src/
uv run mypy src/
```

## Architecture

### Stack-Based Step Engine

The engine processes a LIFO execution stack (`state.execution_stack`). Each `GameStep` subclass implements atomic operations:

```
handler.py: process_resolution_stack()
  ↓
Pop step → step.resolve(state, context)
  ↓
StepResult: {is_finished, requires_input, new_steps, abort_action}
  ↓
If requires_input: pause, return InputRequest to client
If new_steps: push onto stack (reversed for LIFO order)
```

**Key locations:**
- `src/goa2/engine/handler.py` - Main execution loop
- `src/goa2/engine/steps.py` - 50+ GameStep subclasses
- `src/goa2/domain/state.py` - GameState (central mutable world)

### Step Types

- **Selection:** `SelectStep` (unified hex/unit selector with composable filters)
- **Movement:** `MoveUnitStep`, `PushUnitStep`, `PlaceUnitStep`, `SwapUnitsStep`
- **Combat:** `AttackSequenceStep`, `SelectTargetStep`, `ResolveCombatStep`, `DamageStep`
- **Reactions:** `ReactionWindowStep`, `DefenseCardStep`
- **Control:** `FindNextActorStep`, `ResolveCardStep`, `FinalizeHeroTurnStep`

### GameState

Single source of truth in `src/goa2/domain/state.py`:
- `execution_stack` - LIFO action queue
- `execution_context` - transient data between steps (cleared each turn)
- `entity_locations` - unified position tracking (never modify `board.tiles` directly)
- `active_modifiers` - temporary stat buffs/debuffs

### Filter System

Composable unit/hex selection in `src/goa2/engine/filters.py`:

```python
SelectStep(
    target_type="UNIT",
    filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=2)]
)
```

### Card Effect Registry

Hero card logic in `src/goa2/data/heroes/` and `src/goa2/engine/effects.py`:

```python
@register_effect("liquid_leap")
class LiquidLeapEffect(CardEffect):
    def get_steps(self, state, hero, card) -> List[GameStep]: ...
```

## Key Patterns

### Mandatory vs Optional Steps

Per game rules: "If you cannot complete a mandatory step, stop and skip remaining steps."

```python
SelectStep(..., is_mandatory=True)   # Failure → abort_action=True → skip to FinalizeHeroTurnStep
MoveUnitStep(..., is_mandatory=False) # Failure → continue to next step
```

### Context Passing

Steps share data via `execution_context`:
```python
# Step 1 stores
context["target_id"] = selected_unit
# Step 2 retrieves
target_id = context.get("target_id")
```

### Entity IDs

- Static IDs for heroes: `hero_arien`
- Dynamic IDs via `state.create_entity_id("minion")` → `minion_1`, `minion_2`

## Directory Structure

```
src/goa2/
├── domain/          # Data models (Pydantic V2)
│   ├── models/      # Cards, Units, Teams, Modifiers, Enums
│   ├── state.py     # GameState
│   ├── board.py     # Board, Zones, Tiles
│   ├── hex.py       # Hexagonal cube coordinates
│   └── filters.py   # FilterCondition system
├── engine/
│   ├── handler.py   # process_resolution_stack() main loop
│   ├── steps.py     # GameStep subclasses
│   ├── phases.py    # Turn/Phase orchestration
│   ├── rules.py     # Pathfinding, distance, immunity
│   ├── stats.py     # Modifier calculations
│   └── effects.py   # CardEffect registry
├── data/
│   ├── heroes/      # Hero definitions (arien.py, knight.py, rogue.py)
│   └── maps/        # JSON map files
├── scripts/         # Scripts for effects for hero effects

```

## Testing

217 tests organized by domain:
- `tests/domain/` - Models, card lifecycle, entity registration
- `tests/engine/` - Steps, phases, combat, card effects

Integration test pattern:
```python
def test_flow(empty_state):
    push_steps(empty_state, [SomeStep(...)])
    req = process_resolution_stack(empty_state)  # May return input request
    assert req["type"] == "SELECT_UNIT"
    # Provide input and continue...
```
