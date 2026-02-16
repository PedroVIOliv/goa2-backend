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

## Phase 1: Unified Input Contract ✅ COMPLETE

**Fixes:** Pain points #3 (inconsistent format), #4 (unused InputRequest model), #8 (type coercion)
**Goal:** Every input request and response follows a single, typed schema.

### What Was Done

**A. Extended `InputRequest` model** (`src/goa2/domain/input.py`)
- ✅ Added missing types to `InputRequestType` enum: `CHOOSE_ACTION`, `SELECT_CARD_OR_PASS`, `CHOOSE_RESPAWN`, `CHOOSE_RESPAWN_HEX`, `SELECT_OPTION`, `SELECT_CARD`, `SELECT_NUMBER`, `CHOOSE_ACTOR`, `UPGRADE_PHASE`, `CONFIRM_PASSIVE`
- ✅ Added structured fields to `InputRequest`: `prompt`, `options` (unified list), `can_skip`, `player_id`
- ✅ Options are always a list of `InputOption(id: str, text: str, metadata: Dict)` objects
- ✅ Added `InputOption.from_value()` helper to convert various types (Hex, int, dict, etc.) to InputOption
- ✅ `InputRequest` provides dict-like access via `__getitem__()` and `to_dict()` for backwards compatibility

**B. Updated `StepResult`** (`src/goa2/engine/steps.py:41-48`)
- ✅ Changed `input_request: Optional[Dict[str, Any]]` to `input_request: Optional[InputRequest]`
- ✅ Added `events: List[GameEvent] = []` field

**C. Updated all steps** that build `input_request` dicts (~14 locations in `steps.py`)
- ✅ Replaced raw dict construction with `create_input_request(...)` helper or `InputRequest(...)` construction
- ✅ Standardized: options always in `options` field, hexes serialized as dicts in options
- ✅ Split `CHOOSE_RESPAWN` into two distinct types: `CHOOSE_RESPAWN_CONFIRM` and `CHOOSE_RESPAWN_HEX`

**D. Defined `InputResponse` model** (`src/goa2/domain/input.py`)
- ✅ Single response shape: `InputResponse(request_id: str, selection: Any)` - always uses `selection`
- ✅ Added `InputResponse.from_legacy()` helper for backwards compatibility

**E. Updated `playtest.py` handlers**
- ✅ Updated handlers to work with new unified format
- ✅ Reduced from 12+ handlers to ~4 generic handlers using `InputRequest.to_dict()`

### Files Modified
- ✅ `src/goa2/domain/input.py` - extended InputRequest, added InputResponse, InputOption
- ✅ `src/goa2/engine/steps.py` - updated ~14 input_request constructions + StepResult type
- ✅ `src/goa2/scripts/playtest.py` - updated handlers to use new unified format

### Verification
- ✅ All existing tests pass (no behavior change, only contract change)
- ✅ 590 total tests passing
- ✅ playtest.py handlers work with new format

---

## Phase 2: Engine Self-Containment ✅ COMPLETE

**Fixes:** Pain points #2 (direct stack mutation), #6 (client owns game loop)
**Goal:** Client interacts through a single `GameSession` interface, never touches internals.

### What Was Done

**A. Created `submit_input()` function** (`src/goa2/engine/handler.py`)
- ✅ Created `submit_input(state: GameState, response: Union[InputResponse, dict]) -> None`
- ✅ Validates response and sets `step.pending_input` internally (no direct stack mutation by client)
- ✅ Created `StackResult` dataclass to bundle input_request and events
- ✅ Created `process_stack()` function that returns `StackResult` with collected events

**B. Created `GameSession` orchestrator** (`src/goa2/engine/session.py`)
- ✅ Created `GameSession` class that wraps `GameState`
- ✅ Implemented `commit_card(hero_id, card)` for planning phase
- ✅ Implemented `pass_turn(hero_id)` for planning phase
- ✅ Implemented `advance(response: Optional[InputResponse])` for resolution phases
- ✅ Single method `advance()` returns `SessionResult` with types: `INPUT_NEEDED`, `ACTION_COMPLETE`, `PHASE_CHANGED`, `GAME_OVER`
- ✅ Handles planning phase transition internally (after all heroes commit/pass)
- ✅ Client never calls `process_resolution_stack` directly

**C. Refactored `playtest.py` to use `GameSession`**
- ✅ Main loop becomes: get result → display → get user input → submit → repeat
- ✅ Planning phase uses `session.commit_card()` and `session.pass_turn()`
- ✅ Resolution phases use `session.advance()` and `session.advance(response)`

**D. Events integration**
- ✅ `SessionResult` includes `events: List[GameEvent]` field
- ✅ Events collected from all steps between input requests
- ✅ Events returned to client for logging/display

### Files Created/Modified
- ✅ `src/goa2/engine/handler.py` - added `submit_input()`, `process_stack()`, `StackResult`
- ✅ `src/goa2/engine/session.py` - new file, `GameSession` class, `SessionResult` model
- ✅ `src/goa2/scripts/playtest.py` - refactored to use GameSession

### Verification
- ✅ Playtest works identically but through the new interface
- ✅ 26 session/input tests passing
- ✅ All existing tests still pass (590 total)

---

## Phase 3: Event System ✅ COMPLETE

**Fixes:** Pain point #5 (no event/action stream)
**Goal:** Engine communicates what happened, not just what it needs.

### What Was Done

**A. Defined `GameEvent` model** (`src/goa2/domain/events.py`)
- ✅ Created `GameEventType` enum with types:
  - Movement: `UNIT_MOVED`, `UNIT_PLACED`, `UNIT_PUSHED`, `UNITS_SWAPPED`
  - Combat: `COMBAT_RESOLVED`, `UNIT_DEFEATED`, `UNIT_REMOVED`
  - Effects/Markers: `EFFECT_CREATED`, `MARKER_PLACED`, `MARKER_REMOVED`
  - Economy: `GOLD_GAINED`, `LIFE_COUNTER_CHANGED`
  - Turn flow: `TURN_ENDED`, `GAME_OVER`
- ✅ Each event carries: `event_type`, `actor_id`, `target_id`, `from_hex`, `to_hex`, `metadata`
- ✅ Added `_hex_dict(h)` helper to serialize Hex to `{q, r, s}` dict

**B. Added event collection to `StepResult`**
- ✅ New field: `events: List[GameEvent] = []`
- ✅ Steps emit events describing what they did

**C. Collected events in `process_stack()` and `GameSession.advance()`**
- ✅ Accumulate events from all steps between input requests
- ✅ Return them in `StackResult.events` and `SessionResult.events`

**D. Extended `playtest.py` to display events**
- ✅ Events available for logging and display
- ✅ Shows action logs, can animate events ("Arien moves to hex X")

**E. Emitted events from key steps**
- ✅ `MoveUnitStep` → `UNIT_MOVED`
- ✅ `PlaceUnitStep` → `UNIT_PLACED`
- ✅ `PushUnitStep` → `UNIT_PUSHED`
- ✅ `SwapUnitsStep` → `UNITS_SWAPPED`
- ✅ `DefeatUnitStep` → `UNIT_DEFEATED`
- ✅ `RemoveUnitStep` → `UNIT_REMOVED`
- ✅ `CreateEffectStep` → `EFFECT_CREATED`
- ✅ `PlaceMarkerStep` → `MARKER_PLACED`
- ✅ `RemoveMarkerStep` → `MARKER_REMOVED`
- ✅ `GainGoldStep` → `GOLD_GAINED`
- ✅ `ChangeLifeCountersStep` → `LIFE_COUNTER_CHANGED`
- ✅ `ResolveCombatStep` → `COMBAT_RESOLVED`
- ✅ `FinalizeHeroTurnStep` → `TURN_ENDED`
- ✅ `TriggerGameOverStep` → `GAME_OVER`

### Reuse opportunity
- ✅ Aligned `GameEvent` types with existing `GameLogger` categories in playtest.py

### Files Created/Modified
- ✅ `src/goa2/domain/events.py` - new file, GameEvent model, GameEventType enum
- ✅ `src/goa2/engine/steps.py` - added events to ~12 key steps
- ✅ `src/goa2/engine/handler.py` - collect and return events in `process_stack()`
- ✅ `src/goa2/engine/session.py` - surface events in SessionResult

### Verification
- ✅ Playtest displays event log showing what happened each turn
- ✅ Events match actual state changes (cross-reference with state diffs)
- ✅ 23 event tests passing
- ✅ Total: 611 tests passing (includes Phase 1-3 tests + 23 new event tests)

---

## Phase 4: Player-Scoped Views ✅ COMPLETE

**Fixes:** Pain point #7 (no information hiding)
**Goal:** Each player only sees what they're allowed to see.

### What Was Done

**A. Created `GameStateView` builder** (`src/goa2/domain/views.py`)
- ✅ Main function: `build_view(state: GameState, for_hero_id: Optional[HeroID] = None) -> dict`
- ✅ Visibility based purely on `is_facedown` state, not team affiliation
- ✅ Returns serializable dict (no Pydantic model references)
- ✅ Helper functions: `_build_hero_view`, `_build_card_view`, `_build_board_view`, `_build_effects_view`, `_build_markers_view`, `_build_minion_view`, `_build_team_view`

**B. Hero-scoped views**
- ✅ Requesting hero sees all their cards (hand, deck, played, current_turn, discard, ultimate)
- ✅ Other heroes see only faceup cards (using `card.current_*` pattern)
- ✅ Facedown cards hide: `effect_id`, `effect_text`, `primary_action`, `primary_action_value`
- ✅ Faceup cards show all details

**C. Public information**
- ✅ Board, units, effects, markers always visible
- ✅ Discard piles always visible (public info)
- ✅ Team life counters always visible
- ✅ Entity locations always visible

**D. Spectator view**
- ✅ `build_view(state, for_hero_id=None)` shows only public info
- ✅ Faceup cards visible, facedown cards hidden
- ✅ Decks show count only, not card details

**E. API layer integration**
- ✅ Decision: Views called directly by API layer, not embedded in `SessionResult`
- ✅ Rationale: In multiplayer, each HTTP/WebSocket request comes with auth context (which hero)
- ✅ More flexible for different endpoints (public view vs hero-scoped view)

### Reuse opportunity
- ✅ Card masking via `current_*` properties from `card.py` applied at Hero level for hand/deck/played/ultimate cards

### Files Created
- ✅ `src/goa2/domain/views.py` - 258 lines, view builder with helper functions

### Tests
- ✅ `tests/domain/test_views.py` - 21 tests covering:
  - Hero-scoped views (6 tests)
  - Spectator views (3 tests)
  - Card view helper (4 tests)
  - View structure (8 tests)

### Verification
- ✅ View for requesting hero contains their facedown hand cards with full details
- ✅ View for other heroes hides facedown card details (current_* pattern)
- ✅ Spectator view shows no hidden information
- ✅ All public information (board positions, revealed cards, effects) visible to all
- ✅ All 611 tests passing (includes 21 new view tests + 23 event tests + Phase 1-3 tests)

---

## Phase 5: API Server ✅ COMPLETE

**Fixes:** Pain point #1 (no API boundary)
**Goal:** Clients connect over HTTP/WebSocket.

### What Was Done

**A. FastAPI server** (`src/goa2/server/`)
- ✅ `POST /games` - create game, returns game_id + player tokens + spectator token
- ✅ `GET /games/{id}` - get current state view (player-scoped via bearer token auth)
- ✅ `GET /heroes` - list available hero names
- ✅ `POST /games/{id}/cards` - commit a card during planning phase
- ✅ `POST /games/{id}/pass` - pass turn during planning phase
- ✅ `POST /games/{id}/input` - submit InputResponse during resolution
- ✅ `POST /games/{id}/advance` - advance resolution without input
- ✅ `WebSocket /games/{id}/ws` - real-time bidirectional game interaction (COMMIT_CARD, SUBMIT_INPUT, PASS_TURN, GET_VIEW)

**B. Game session registry** (`src/goa2/server/registry.py`)
- ✅ In-memory dict of `game_id -> ManagedGame`
- ✅ Bearer-token authentication per player + spectator tokens
- ✅ Per-game async locks for concurrency safety
- ✅ WebSocket connection tracking per game

**C. Request/response serialization** (`src/goa2/server/models.py`)
- ✅ Pydantic request/response models with automatic OpenAPI schema
- ✅ `ActionResultResponse` with result_type, current_phase, events, input_request, winner
- ✅ `GameViewResponse` with player-scoped view + pending input_request

**D. Error handling** (`src/goa2/server/errors.py`)
- ✅ Custom exceptions: `GameNotFoundError`, `CardNotInHandError`, `InvalidPhaseError`, `NotYourTurnError`
- ✅ Proper HTTP status codes (401, 403, 404) for auth/game/card errors

**E. WebSocket features** (`src/goa2/server/ws.py`)
- ✅ Player-scoped state broadcast after mutations
- ✅ Spectator restrictions (can only GET_VIEW)
- ✅ Error messages for invalid JSON, unknown message types

### Files Created
- ✅ `src/goa2/server/__init__.py`
- ✅ `src/goa2/server/app.py` - FastAPI app with lifespan
- ✅ `src/goa2/server/routes_heroes.py` - hero listing endpoint
- ✅ `src/goa2/server/routes_games.py` - game CRUD + action endpoints
- ✅ `src/goa2/server/ws.py` - WebSocket handler with broadcast
- ✅ `src/goa2/server/auth.py` - bearer token auth dependency
- ✅ `src/goa2/server/registry.py` - game session management
- ✅ `src/goa2/server/models.py` - request/response Pydantic models
- ✅ `src/goa2/server/errors.py` - custom exception classes

### Tests
- ✅ `tests/server/test_server_rest.py` - 13 REST integration tests
- ✅ `tests/server/test_server_ws.py` - 11 WebSocket integration tests

### Verification
- ✅ Create game, commit cards, trigger phase transitions via REST
- ✅ Full planning flow via WebSocket (both players commit → phase change)
- ✅ Spectator access via both REST and WebSocket
- ✅ Auth enforcement (401/403 for missing/wrong tokens)
- ✅ OpenAPI docs auto-generated at `/docs`
- ✅ 650 tests passing

---

## Phase 6: State Persistence ✅ COMPLETE

**Fixes:** Pain point #9 (no save/load)
**Goal:** Games survive server restarts; replays are possible.

### What Was Done

**A. Fixed StepType discriminator collisions** (`src/goa2/domain/models/enums.py`)
- ✅ Added 6 unique `StepType` values to replace shared `GENERIC`: `PLACE_MARKER`, `REMOVE_MARKER`, `DISCARD_CARD`, `FORCE_DISCARD`, `FORCE_DISCARD_OR_DEFEAT`, `COMBINE_BOOLEAN_CONTEXT`
- ✅ Updated corresponding step classes in `steps.py`

**B. Discriminated union types** (`src/goa2/engine/step_types.py`)
- ✅ Defined `AnyStep` union covering all 53 step subclasses with `Tag` + callable `Discriminator` pattern
- ✅ Defined `AnyFilter` union covering all 19 filter subclasses
- ✅ Patched `model_fields` on `GameState`, `SelectStep`, `MultiSelectStep`, `AttackSequenceStep`, `MayRepeatNTimesStep`, `ForEachStep`
- ✅ Sealing module imported from `handler.py` to ensure patching before engine use

**C. Persistence module** (`src/goa2/engine/persistence.py`)
- ✅ `save_game()` — atomic write (tmpfile + `os.replace`) of game state to JSON
- ✅ `load_game()` — deserialize JSON, reconstruct `GameSession` + `ManagedGame`, re-derive `last_result` via `process_stack()`
- ✅ `load_all_games()` — glob `*.json` in save directory, skip corrupt files
- ✅ `delete_game_save()` — remove save file

**D. Auto-save integration**
- ✅ `GameRegistry` accepts `save_dir` param, auto-saves on game creation
- ✅ REST endpoints auto-save after every mutation (commit_card, pass_turn, submit_input, advance)
- ✅ WebSocket handler auto-saves after mutations (COMMIT_CARD, SUBMIT_INPUT, PASS_TURN)
- ✅ `GOA2_SAVE_DIR` env var configures save directory (empty = disabled)
- ✅ Server restores all games from save directory on startup

### Files Created
- ✅ `src/goa2/engine/step_types.py` - AnyStep/AnyFilter unions, model patching
- ✅ `src/goa2/engine/persistence.py` - save/load functions

### Files Modified
- ✅ `src/goa2/domain/models/enums.py` - 6 new StepType values
- ✅ `src/goa2/engine/steps.py` - unique StepType per class
- ✅ `src/goa2/engine/handler.py` - import step_types for patching
- ✅ `src/goa2/server/registry.py` - save_dir, save_game, restore_all
- ✅ `src/goa2/server/app.py` - GOA2_SAVE_DIR, restore on startup
- ✅ `src/goa2/server/routes_games.py` - auto-save after mutations
- ✅ `src/goa2/server/ws.py` - auto-save after mutations

### Tests
- ✅ `tests/engine/test_persistence.py` - 15 tests (round-trip, filters, discriminators, mid-resolution, corrupt files)
- ✅ `tests/server/test_server_persistence.py` - 8 tests (save file creation, restart survival, WS reconnection, multi-game, disabled persistence)

### Verification
- ✅ Save mid-game, restart server, load, continue playing
- ✅ All step/filter types round-trip through JSON correctly
- ✅ WebSocket reconnection works after restart with same tokens
- ✅ 673 tests passing

---

## Dependency Graph

```
✅ Phase 1: Input Contract  (no dependencies)
     |
     v
✅ Phase 2: Engine Session  (depends on Phase 1)
     |         \
     v          v
✅ Phase 3:    ✅ Phase 4:     (independent, can run in parallel)
   Events      Views
     \         /
      v       v
✅ Phase 5: API Server      (depends on Phases 1-4)
     |
     v
✅ Phase 6: Persistence     (depends on Phase 5)
```

---

## What a Client Sees After Each Phase

| After Phase | Client can... |
|-------------|---------------|
| ✅ 1 | Parse input requests with a single generic handler (typed schema) |
| ✅ 2 | Interact through `GameSession` without touching engine internals |
| ✅ 3 | Show action logs, animate events ("Arien moves to hex X") |
| ✅ 4 | Only see information they're allowed to see |
| ✅ 5 | Connect over HTTP/WebSocket from any language |
| ✅ 6 | Reconnect to games, replay matches |
