# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Guards of Atlantis II (GoA2) backend - a deterministic, stack-based game engine for a hexagonal tactical game, with a FastAPI server layer for client integration. Built with Python 3.11+ and Pydantic V2.

**Core Philosophy:** "Logic as Data" - uses atomic game steps pushed onto a LIFO execution stack instead of nested function calls, enabling pauseable mid-action gameplay with input requests.

For detailed architecture, module guide, and data flows, see [docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md).
For client integration details, see [docs/CLIENT_INTEGRATION_GUIDE.md](docs/CLIENT_INTEGRATION_GUIDE.md).

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

# Start the API server (development)
PYTHONPATH=src uv run uvicorn goa2.server.app:create_app --factory --reload

# Run server tests only
PYTHONPATH=src uv run pytest tests/server/ -q

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

## Server & API Layer

The server package (`src/goa2/server/`) wraps the engine with a FastAPI application providing REST and WebSocket interfaces for client integration.

**Key features:**
- **REST API** — Create games, get player-scoped views, commit cards, pass turns, submit input, advance game state (`routes_games.py`, `routes_heroes.py`)
- **WebSocket** — Real-time game interaction with automatic broadcast of player-scoped state updates to all connected clients (`ws.py`)
- **Bearer-token auth** — Each hero gets a unique token at game creation; a separate spectator token provides read-only access (`auth.py`)
- **Player-scoped views** — `build_view()` filters game state per player (own cards visible, opponents' facedown cards hidden) (`domain/views.py`)
- **Auto-save persistence** — Game state is saved to JSON after every mutation using atomic writes; games are restored on server restart (`engine/persistence.py`)

See [docs/CLIENT_INTEGRATION_GUIDE.md](docs/CLIENT_INTEGRATION_GUIDE.md) for the full API reference and integration guide.

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

## Client-Readiness Rules

These rules protect the contract between the backend and client applications. Breaking them will break frontend clients.

1. **Steps MUST use `InputRequest`** (from `domain/input.py`) — never return raw dicts for input requests. Steps must also emit `GameEvent`s for any observable state changes.

2. **Never expose `GameState` directly** — always use `build_view()` from `domain/views.py` to produce player-scoped views. Clients must never see another player's facedown cards.

3. **New steps need a unique `StepType`** — add the enum value to `StepType` in `domain/models/enums.py`, then add the step to the `AnyStep` union in `engine/step_types.py`. Without this, the step cannot be serialized/deserialized (persistence breaks).

4. **New filters need a unique `FilterType`** — add the enum value to `FilterType` in `domain/models/enums.py`, then add the filter to the `AnyFilter` union in `engine/step_types.py`.

5. **Don't change response model shapes** without updating the client integration guide (`docs/CLIENT_INTEGRATION_GUIDE.md`). The response models in `server/models.py` are the client contract.

6. **Server tests must pass** — run `PYTHONPATH=src uv run pytest tests/server/ -q` before merging any server-related changes.

## Client-Facing Contract

These components form the public API that clients depend on. Breaking changes here break the frontend.

| Component | File | What's Public |
|-----------|------|---------------|
| Response models | `server/models.py` | `CreateGameResponse`, `GameViewResponse`, `ActionResultResponse`, `ErrorResponse` shapes |
| Input contract | `domain/input.py` | `InputRequest.to_dict()` output shape, `InputResponse` fields |
| Events | `domain/events.py` | `GameEvent` fields, `GameEventType` enum values |
| Views | `domain/views.py` | `build_view()` output structure (teams, board, effects, markers) |
| REST endpoints | `server/routes_games.py` | URL paths, HTTP methods, request/response bodies |
| WebSocket protocol | `server/ws.py` | Message types (`STATE_UPDATE`, `ACTION_RESULT`, `ERROR`), message shapes |

**Do not rename, remove, or restructure these without updating the client integration guide.**

## Input Request Types

When a step needs player input, use `create_input_request()` from `domain/input.py`:

| Type | Use Case | Selection Value |
|------|----------|-----------------|
| `SELECT_UNIT` | Choose unit on board | Unit ID string (`"minion_1"`) |
| `SELECT_HEX` | Choose hex on board | Hex dict (`{"q": 0, "r": 0, "s": 0}`) |
| `SELECT_CARD` | Choose card from hand | Card ID string |
| `SELECT_NUMBER` | Choose numeric value | Integer |
| `CHOOSE_ACTION` | Choose named action | Option ID string |
| `SELECT_OPTION` | Generic choice | Option ID string |
| `CONFIRM_PASSIVE` | Yes/No prompt | `"YES"` or `"NO"` |

**Skip behavior:** For optional selections, clients submit `"SKIP"` (string), not `null`.

**Team-level input:** Use `player_id=f"team:{TeamColor.RED.value}"` for decisions any team member can make. The `server/errors.py:validate_input_turn()` helper handles this format.

For full parameters, see `domain/input.py:create_input_request()`.

## Where to Hook New Game Logic

| Trigger | Step to Modify | How |
|---------|----------------|-----|
| End of hero turn | `FinalizeHeroTurnStep` | Add to `new_steps` before `FindNextActorStep` |
| End of round | `EndPhaseStep` | Add to `_resolve_*` methods |
| After card effect | Card effect class | Add steps in `build_steps()` |
| During attack | `AttackSequenceStep` | Add pre/post steps via `new_steps` |
| On unit movement | `MoveUnitStep` / `PlaceUnitStep` | Emit events or spawn follow-up steps in `resolve()` |

**Pattern:** Return `StepResult(new_steps=[...])` from the appropriate step's `resolve()` method.

## Client API Contract Ownership

The `CLIENT_INTEGRATION_GUIDE.md` is the frontend's source of truth for the API.

**Backend owns this document.** When you change any of the following, update it:
- New `InputRequestType` values or fields
- New `GameEventType` values or `GameEvent` fields
- New response shapes in `server/models.py`
- New `player_id` formats (e.g., `team:XXX`)
- Changes to special values (e.g., `"SKIP"` for skipping)

## Before Making Changes

1. **Read before writing** — Always read the files you intend to modify. Understand existing patterns before changing code.
2. **Run tests before and after** — Run `PYTHONPATH=src uv run pytest tests/ -q` to confirm your changes don't break anything. For server-only changes, `tests/server/` is sufficient.
3. **Check if you're touching client contracts** — If your change affects anything in `server/models.py`, `domain/input.py`, `domain/events.py`, or `domain/views.py`, you are modifying the client-facing contract. Proceed with extra care and update `docs/CLIENT_INTEGRATION_GUIDE.md` accordingly.

## Adding New Game Steps

Checklist:

1. Add a unique `StepType` enum value in `domain/models/enums.py`
2. Create the step class in `engine/steps.py` with `type: StepType = StepType.YOUR_TYPE`
3. Add the step to the `AnyStep` union in `engine/step_types.py` (import + `Annotated[YourStep, Tag(...)]`)
4. Emit `GameEvent`s for any observable state changes (movement, combat, defeat, etc.)
5. Use `InputRequest` (via `create_input_request()`) if the step needs player input — never return raw dicts
6. Write tests in `tests/engine/`

If any of steps 1-3 are skipped, **persistence will break** — the step cannot be serialized/deserialized from JSON.

## Adding New Filters

Checklist:

1. Add a unique `FilterType` enum value in `domain/models/enums.py`
2. Create the filter class in `engine/filters.py` with `type: FilterType = FilterType.YOUR_TYPE`
3. Add the filter to the `AnyFilter` union in `engine/step_types.py` (import + `Annotated[YourFilter, Tag(...)]`)
4. Write tests in `tests/engine/`

Same persistence concern applies — missing from the union means it can't round-trip through JSON.

## Server Changes

When modifying the server layer (`src/goa2/server/`):

1. **Auth** — All player-facing endpoints require bearer-token auth. Spectator tokens have read-only access. Don't create endpoints that bypass auth.
2. **Auto-save** — Call `registry.save_game(game_id)` after any state mutation. Both REST and WebSocket handlers do this already; maintain the pattern.
3. **Broadcast** — After mutations via WebSocket, call `broadcast(game, registry)` so all connected clients get updated views.
4. **Player-scoped views** — Always use `build_view(state, for_hero_id=hero_id)` when sending state to a specific player. Spectators get `for_hero_id=None`.
5. **Update the client guide** — If you add/change/remove an endpoint or modify response shapes, update `docs/CLIENT_INTEGRATION_GUIDE.md`.
6. **Add server tests** — REST endpoint tests go in `tests/server/test_server_rest.py`, WebSocket tests in `test_server_ws.py`.

## Common Pitfalls

- **Forgetting `step_types.py` unions** — The most common cause of persistence failures. Every new `GameStep` subclass needs to be in `AnyStep`, every new `FilterCondition` subclass needs to be in `AnyFilter`.
- **Using `StepType.GENERIC`** — Don't. Every step needs its own unique `StepType` value for the discriminated union to work.
- **Not emitting events** — Steps that change observable state (move units, resolve combat, place markers, etc.) must emit `GameEvent`s. Without events, clients can't animate or log actions.
- **Exposing `GameState` directly** — Never send `state.model_dump()` to a client. Always go through `build_view()` to enforce visibility rules (facedown cards, etc.).
- **Modifying `board.tiles` directly for positions** — Use `state.entity_locations` for position tracking. The tile `occupant_id` is derived from entity_locations.
- **Forgetting `model_rebuild()`** — If you add a step/filter that contains `List[GameStep]` or `List[FilterCondition]` fields, you need to patch those fields in `step_types.py` and call `model_rebuild(force=True)`.

## Directory Structure

```
src/goa2/
├── domain/            # Data models (Pydantic V2)
│   ├── models/        # Cards, Units, Teams, Modifiers, Enums
│   ├── state.py       # GameState
│   ├── board.py       # Board, Zones, Tiles
│   ├── hex.py         # Hexagonal cube coordinates
│   ├── input.py       # InputRequest/InputResponse contract
│   ├── events.py      # GameEvent/GameEventType
│   └── views.py       # build_view() player-scoped filtering
├── engine/
│   ├── handler.py     # process_stack() / process_resolution_stack() main loop
│   ├── steps.py       # GameStep subclasses
│   ├── step_types.py  # AnyStep/AnyFilter unions for serialization
│   ├── filters.py     # FilterCondition system
│   ├── session.py     # GameSession client-facing interface
│   ├── persistence.py # Save/load game state to JSON
│   ├── phases.py      # Turn/Phase orchestration
│   ├── rules.py       # Pathfinding, distance, immunity
│   ├── stats.py       # Modifier calculations
│   └── effects.py     # CardEffect registry
├── server/
│   ├── app.py         # FastAPI application factory
│   ├── auth.py        # Bearer-token authentication
│   ├── models.py      # Request/response Pydantic models
│   ├── routes_games.py # REST game endpoints
│   ├── routes_heroes.py # GET /heroes endpoint
│   ├── ws.py          # WebSocket handler + broadcast
│   ├── registry.py    # In-memory game registry
│   └── errors.py      # Server exception classes
├── data/
│   ├── heroes/        # Hero definitions + registry
│   └── maps/          # JSON map files
├── scripts/           # Scripts for effects for hero effects
```

## Testing

692 tests organized by domain:
- `tests/domain/` - Models, card lifecycle, entity registration
- `tests/engine/` - Steps, phases, combat, card effects, session, input contract
- `tests/server/` - REST endpoints, WebSocket protocol, auth, registry, persistence

Integration test pattern:
```python
def test_flow(empty_state):
    push_steps(empty_state, [SomeStep(...)])
    req = process_resolution_stack(empty_state)  # May return input request
    assert req["type"] == "SELECT_UNIT"
    # Provide input and continue...
```
