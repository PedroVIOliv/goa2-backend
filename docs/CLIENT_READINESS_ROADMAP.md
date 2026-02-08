# Backend Client-Readiness Roadmap

## Context

The GoA2 backend engine is functionally solid but has no client-facing abstraction layer. The only "client" (`playtest.py`) interacts by directly importing Python modules, mutating `GameState`, and reaching into the execution stack. This roadmap addresses 9 identified pain points in dependency order, so each phase builds on the previous one and the engine becomes progressively more client-friendly.

---

## Pain Points Summary

| # | Pain Point | Severity | Description |
|---|---|---|---|
| 1 | No API boundary | CRITICAL | No server/endpoints. Clients must import Python directly. |
| 2 | Direct stack mutation for input | CRITICAL | Client must reach into `execution_stack[-1].pending_input`. No validation. |
| 3 | Inconsistent input request format | HIGH | 12+ request types each with unique field names and response keys. |
| 4 | InputRequest model unused | HIGH | Typed model exists in `domain/input.py` but all steps build raw dicts. |
| 5 | No event/action stream | HIGH | Engine never says "X attacked Y". Client must diff state snapshots. |
| 6 | Client owns game loop | MEDIUM | Phase orchestration lives in playtest.py, not the engine. |
| 7 | No player-scoped views | MEDIUM | Full state including opponent hands is exposed. |
| 8 | Type coercion on client | LOW | Hexes arrive as objects or dicts depending on code path. |
| 9 | No persistence | LOW | No save/load, no reconnection, no replays. |

---

## Phase 1: Unified Input Contract

**Fixes:** Pain points #3 (inconsistent format), #4 (unused InputRequest model), #8 (type coercion)
**Goal:** Every input request and response follows a single, typed schema.

### What to do

**A. Extend `InputRequest` model** (`src/goa2/domain/input.py`)
- Add missing types to `InputRequestType` enum: `CHOOSE_ACTION`, `SELECT_CARD_OR_PASS`, `CHOOSE_RESPAWN`, `SELECT_OPTION`, `SELECT_CARD`, `SELECT_NUMBER`, `CHOOSE_ACTOR`, `UPGRADE_PHASE`, `CONFIRM_PASSIVE`
- Add structured fields to `InputRequest`: `prompt`, `options` (unified list), `can_skip`, `player_id`
- Options are always a list of `InputOption(id: str, text: str, metadata: Dict)` objects

**B. Update `StepResult`** (`src/goa2/engine/steps.py:41-48`)
- Change `input_request: Optional[Dict[str, Any]]` to `input_request: Optional[InputRequest]`

**C. Update all steps** that build `input_request` dicts (~14 locations in `steps.py`)
- Replace raw dict construction with `InputRequest(...)` construction
- Standardize: options always in `options` field, hexes serialized as dicts in options
- Split `CHOOSE_RESPAWN` into two distinct types: `CHOOSE_RESPAWN_CONFIRM` and `CHOOSE_RESPAWN_HEX`

**D. Define `InputResponse` model** (new, in `src/goa2/domain/input.py`)
- Single response shape: `InputResponse(request_id: str, selection: Any)` - always uses `selection`

### Files to modify
- `src/goa2/domain/input.py` - extend InputRequest, add InputResponse
- `src/goa2/engine/steps.py` - update ~14 input_request constructions + StepResult type
- `src/goa2/scripts/playtest.py` - update handlers to use new unified format

### Verification
- All existing tests pass (no behavior change, only contract change)
- `playtest.py` handlers can be reduced from 12+ to ~4 generic handlers

---

## Phase 2: Engine Self-Containment

**Fixes:** Pain points #2 (direct stack mutation), #6 (client owns game loop)
**Goal:** Client interacts through a single `GameSession` interface, never touches internals.

### What to do

**A. Create `submit_input()` function** (`src/goa2/engine/handler.py`)
```python
def submit_input(state: GameState, response: InputResponse) -> None:
    """Validate and apply player input to the pending step."""
    # Validates response matches pending request
    # Sets step.pending_input internally
```

**B. Create `GameSession` orchestrator** (new: `src/goa2/engine/session.py`)
- Wraps `GameState` + owns the game loop
- Single method: `advance() -> SessionResult` which returns either:
  - `SessionResult(type="INPUT_NEEDED", request=InputRequest, state_view=...)`
  - `SessionResult(type="PHASE_COMPLETE", state_view=...)`
  - `SessionResult(type="GAME_OVER", state_view=...)`
- Handles planning phase internally (wraps `commit_card` / `pass_turn`)
- Client never calls `process_resolution_stack` directly

**C. Simplify `playtest.py`** to use `GameSession`
- Main loop becomes: get result -> display -> get user input -> submit -> repeat

### Files to modify
- `src/goa2/engine/handler.py` - add `submit_input()`
- `src/goa2/engine/session.py` - new file, GameSession class
- `src/goa2/scripts/playtest.py` - refactor to use GameSession

### Verification
- Playtest works identically but through the new interface
- All tests pass

---

## Phase 3: Event System

**Fixes:** Pain point #5 (no event/action stream)
**Goal:** Engine communicates what happened, not just what it needs.

### What to do

**A. Define `GameEvent` model** (new: `src/goa2/domain/events.py`)
- Types: `UNIT_MOVED`, `UNIT_ATTACKED`, `UNIT_DEFEATED`, `EFFECT_CREATED`, `EFFECT_EXPIRED`, `CARD_PLAYED`, `CARD_REVEALED`, `PHASE_CHANGED`, `MARKER_PLACED`, etc.
- Each event carries: `event_type`, `actor_id`, `target_id`, `from_hex`, `to_hex`, `metadata`

**B. Add event collection to `StepResult`**
- New field: `events: List[GameEvent] = []`
- Steps emit events describing what they did (e.g., `MoveUnitStep` emits `UNIT_MOVED`)

**C. Collect events in `GameSession.advance()`**
- Accumulate events from all steps between input requests
- Return them in `SessionResult.events`

**D. Extend `playtest.py`** to display events
- Show "Arien attacks Wasp for 3 damage" instead of just re-rendering board

### Reuse opportunity
- `GameLogger` in playtest.py already defines event categories (GAME_START, INPUT_REQUEST, ACTION, etc.) - align `GameEvent` types with these

### Files to modify
- `src/goa2/domain/events.py` - new file
- `src/goa2/engine/steps.py` - add events to key steps (MoveUnitStep, AttackSequenceStep, DefeatUnitStep, CreateEffectStep, etc.)
- `src/goa2/engine/handler.py` - collect events
- `src/goa2/engine/session.py` - surface events in SessionResult

### Verification
- Playtest displays event log showing what happened each turn
- Events match actual state changes (cross-reference with state diffs)

---

## Phase 4: Player-Scoped Views

**Fixes:** Pain point #7 (no information hiding)
**Goal:** Each player only sees what they're allowed to see.

### What to do

**A. Create `GameStateView` builder** (new: `src/goa2/domain/views.py`)
- `build_view(state: GameState, for_team: TeamColor) -> dict`
- Masks opponent hands (only show card count)
- Masks facedown cards (use existing `current_*` pattern from `card.py:60-113`)
- Shows full info for own team
- Returns serializable dict (no Pydantic model references)

**B. Integrate into `GameSession`**
- `SessionResult.state_view` uses `build_view()` scoped to the requesting player

**C. Create spectator view**
- `build_view(state, for_team=None)` shows public info only

### Reuse opportunity
- Card masking via `current_*` properties is already complete in `card.py`
- Extend this pattern to Hero level (mask hand contents)

### Files to modify
- `src/goa2/domain/views.py` - new file
- `src/goa2/engine/session.py` - use views in SessionResult

### Verification
- View for RED team doesn't contain BLUE hand card details
- View for spectator shows no hidden information
- All public information (board positions, revealed cards, effects) is visible to all

---

## Phase 5: API Server

**Fixes:** Pain point #1 (no API boundary)
**Goal:** Clients connect over HTTP/WebSocket.

### What to do

**A. FastAPI server** (new: `src/goa2/server/`)
- `POST /games` - create game, returns game_id
- `GET /games/{id}` - get current state view (player-scoped via auth)
- `POST /games/{id}/input` - submit InputResponse
- `WebSocket /games/{id}/ws` - real-time event stream + input requests

**B. Game session registry**
- In-memory dict of `game_id -> GameSession`
- Player authentication (simple token-based for now)

**C. Request/response serialization**
- All models are Pydantic, so automatic OpenAPI schema generation
- Clients get auto-generated TypeScript types via OpenAPI

### Dependencies
- Phases 1-4 must be complete (clean contracts, session abstraction, events, views)
- FastAPI is already in dependencies

### Files to create
- `src/goa2/server/__init__.py`
- `src/goa2/server/app.py` - FastAPI app
- `src/goa2/server/routes.py` - endpoints
- `src/goa2/server/auth.py` - simple player auth
- `src/goa2/server/registry.py` - game session management

### Verification
- Can create a game via `curl POST /games`
- Can play a full turn via HTTP requests
- WebSocket receives events in real-time
- OpenAPI docs auto-generated at `/docs`

---

## Phase 6: State Persistence

**Fixes:** Pain point #9 (no save/load)
**Goal:** Games survive server restarts; replays are possible.

### What to do

- Serialize `GameState` (challenge: `execution_stack` contains `GameStep` instances)
- Option A: Make all GameSteps fully serializable (they're already Pydantic models)
- Option B: Checkpoint at phase boundaries when stack is empty
- Add save/load to `GameSession`
- Add reconnection endpoint to server

### Verification
- Save mid-game, restart server, load, continue playing
- Replay a game from event log

---

## Dependency Graph

```
Phase 1: Input Contract  (no dependencies)
    |
    v
Phase 2: Engine Session  (depends on Phase 1)
    |         \
    v          v
Phase 3:    Phase 4:     (independent, can run in parallel)
Events      Views
    \         /
     v       v
Phase 5: API Server      (depends on Phases 1-4)
    |
    v
Phase 6: Persistence     (depends on Phase 5)
```

---

## What a Client Sees After Each Phase

| After Phase | Client can... |
|-------------|---------------|
| 1 | Parse input requests with a single generic handler (typed schema) |
| 2 | Interact through `GameSession` without touching engine internals |
| 3 | Show action logs, animate events ("Arien moves to hex X") |
| 4 | Only see information they're allowed to see |
| 5 | Connect over HTTP/WebSocket from any language |
| 6 | Reconnect to games, replay matches |
