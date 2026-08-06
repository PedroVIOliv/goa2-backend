# AI Backend Integration Implementation Plan

**Goal:** Allow server-managed AI heroes to play complete live games against humans or other bots through the same engine, persistence, replay, clock, and broadcast paths as human players.
**Architecture:** Keep decision policy in `automata` and add a server-owned bot coordinator that computes against cloned state outside server locks, validates that the decision is still current, and applies one legal action through `GameSession`. Represent bots as persisted `ManagedGame` metadata rather than changing `GameState` or hero models, and release Random/Heuristic bots before enabling bounded ISMCTS.
**Tech stack:** Python 3.11+, asyncio, FastAPI, Pydantic V2, existing `GameSession`, `ManagedGame`, persistence, WebSocket, replay, and time-control infrastructure.

## Scope And Invariants

- Support full bot-vs-bot and mixed human/bot games created through the normal server API.
- Keep engine rules authoritative. Bot code must use `GameSession.commit_card()`, `finish_planning()`, `pass_turn()`, and `advance()` rather than mutating `GameState` directly.
- Never hold `ManagedGame.lock` or `outbound_lock` while an agent computes.
- Apply at most one bot decision per locked mutation, persist it, record it, broadcast it, yield to the event loop, and then schedule the next decision.
- Reject stale decisions by checking the expected phase, responsible hero, planning state, and exact `InputRequest.id` where applicable.
- Persist serializable bot configuration, never live agent instances.
- Preserve current response shapes and hero-token behavior. Bot heroes may still receive tokens unless a later contract explicitly changes that.
- Random and Heuristic bots are the first production milestone. ISMCTS remains opt-in until it has bounded execution and mixed-team correctness.

## Non-Goals

- Draft-mode bots.
- Learned policy or value models.
- Distributed workers or a process-pool search service.
- Client controls for changing a bot after game creation.
- New bot-specific fields in `GameState`, `Hero`, player-scoped views, or engine input requests.

### Task 1: Normalize Agent Decisions

**Files (footprint):**
- Modify: `src/automata/agents/base.py`
- Modify: `src/automata/agents/random_agent.py`
- Modify: `src/automata/agents/heuristic_agent.py`
- Modify: `src/automata/search/agent.py`
- Test: `tests/ai/test_heuristic.py`
- Test: `tests/ai/test_ismcts.py`

**Depends on:** none
**Parallel group:** A

**What:** Make agent output match the engine's authoritative input and planning vocabulary.
**Interface:** Retain `Agent.choose_card(state, hero) -> Card | None` for policy selection, but use `goa2.domain.input.selection_value()` for converting an `InputOption` to a submitted value. Add a small typed planning decision model that can represent `COMMIT`, `FINISH`, and `PASS` without overloading `None` for multiple meanings.
**Behavior:** Numeric selections must be submitted as integers, hex options as hex dictionaries, ordinary options as IDs, and skips as `"SKIP"`. Planning decisions must distinguish an empty-hand pass from ending a legal multi-card planning sequence.
**Tests:** Cover numeric, hex, raw metadata, skip, commit, finish, and pass decisions. Existing Random, Heuristic, and ISMCTS choices must remain legal.
**Validation:** `PYTHONPATH=src uv run pytest tests/ai/test_heuristic.py tests/ai/test_ismcts.py -q`

### Task 2: Extract A One-Decision Driver

**Files (footprint):**
- Create: `src/automata/runtime/driver.py`
- Modify: `src/automata/runtime/__init__.py`
- Modify: `src/automata/runtime/harness.py`
- Test: `tests/ai/test_harness_smoke.py`

**Depends on:** Task 1
**Parallel group:** B

**What:** Extract the headless harness's decision ownership and application logic into a reusable, server-neutral driver.
**Interface:** Provide a typed function that inspects a state/result pair and returns either no bot decision or one planning/input decision for an explicitly mapped hero. Keep mutation application separate so the live server can apply through its own locked lifecycle.
**Behavior:** Never fall back to an arbitrary agent when a hero mapping is absent. Correctly finish Emmitt's multi-card planning, scope upgrade choices to bot-owned pending heroes, and stop when the next decision belongs to a human. Refactor `run_game()` to use this driver so headless and server play share decision semantics.
**Tests:** Cover a missing agent mapping, a mixed human/bot team, Emmitt finishing planning after the allowed cards, team-addressed input, scoped upgrade choices, and a complete bot-vs-bot smoke game.
**Validation:** `PYTHONPATH=src uv run pytest tests/ai/test_harness_smoke.py -q`

### Task 3: Anchor ISMCTS To The Requested Hero

**Files (footprint):**
- Modify: `src/automata/search/agent.py`
- Modify: `src/automata/search/ismcts.py`
- Test: `tests/ai/test_ismcts.py`
- Test: `tests/ai/test_ismcts_prior.py`
- Test: `tests/ai/test_puct.py`

**Depends on:** Task 1
**Parallel group:** B

**What:** Remove the current assumption that an ISMCTS agent controls every hero on its team.
**Interface:** Pass an explicit root decision owner and decision kind into search/simulator advancement. Opponent and teammate rollout policies remain configurable, but they cannot replace the requested root decision.
**Behavior:** Search must stop at the requested bot hero's planning decision or the exact pending input request. A still-uncommitted human teammate must not become the root action. Team-addressed requests may be handled only when the configured bot is an eligible responder.
**Tests:** Cover a bot with an uncommitted human teammate, multiple bots on one team, team-addressed input, and unchanged single-team self-play behavior.
**Validation:** `PYTHONPATH=src uv run pytest tests/ai/test_ismcts.py tests/ai/test_ismcts_prior.py tests/ai/test_puct.py -q`

### Task 4: Add Persisted Bot Metadata

**Files (footprint):**
- Create: `src/goa2/server/bot_models.py`
- Modify: `src/goa2/server/registry.py`
- Modify: `src/goa2/engine/persistence.py`
- Test: `tests/server/test_registry.py`
- Test: `tests/server/test_server_persistence.py`

**Depends on:** none
**Parallel group:** A

**What:** Represent bot ownership and configuration in the managed server game without modifying engine state.
**Interface:** Add a Pydantic `BotSpec` with a constrained agent kind (`random`, `heuristic`, `ismcts`) and optional bounded search settings. Add `bot_specs: dict[str, BotSpec]` and `bot_task: asyncio.Task[None] | None` to `ManagedGame`; only `bot_specs` is serialized.
**Behavior:** Validate that every bot hero belongs to the game roster. Save and restore bot specifications with the existing state/tokens payload. Restored games must not deserialize live agent objects or tasks. Existing save files without bot metadata must load unchanged.
**Tests:** Cover metadata round-trip, legacy save compatibility, invalid hero IDs, task exclusion from persistence, and restored configuration equality.
**Validation:** `PYTHONPATH=src uv run pytest tests/server/test_registry.py tests/server/test_server_persistence.py -q`

### Task 5: Implement The Bot Coordinator

**Files (footprint):**
- Create: `src/goa2/server/bots.py`
- Create: `tests/server/test_server_bots.py`
- Modify: `src/goa2/server/registry.py`

**Depends on:** Task 2, Task 3, Task 4
**Parallel group:** C

**What:** Build an idempotent asynchronous coordinator that computes and applies one bot decision at a time.
**Interface:** Provide an agent factory from `BotSpec`, `schedule_bot_drive(game, registry) -> None`, and an internal async worker. The worker snapshots the state/request under `game.lock`, computes via `asyncio.to_thread()`, and applies through `GameSession` after stale validation.
**Behavior:** Keep one `bot_task` per game. Do not hold locks during policy computation. Acquire locks in the established `outbound_lock` then `game.lock` order when applying. Validate request IDs and planning eligibility, discard stale outputs, use normal replay/log/save/finalization behavior, capture recipient-scoped broadcasts while locked, send after unlocking, and yield before scheduling another action. Agent errors or illegal output must be logged and must leave the game recoverable.
**Tests:** Cover one-action application, duplicate scheduling, stale request rejection, a human action racing bot computation, agent exceptions, illegal choices, bot-vs-bot continuation, stopping at a human decision, and cancellation during shutdown.
**Validation:** `PYTHONPATH=src uv run pytest tests/server/test_server_bots.py -q`

### Task 6: Wire Server Lifecycle And Time Controls

**Files (footprint):**
- Modify: `src/goa2/server/app.py`
- Modify: `src/goa2/server/routes_games.py`
- Modify: `src/goa2/server/ws.py`
- Modify: `src/goa2/server/time_control.py`
- Modify: `tests/server/test_server_bots.py`
- Test: `tests/server/test_server_rest.py`
- Test: `tests/server/test_server_ws.py`

**Depends on:** Task 5
**Parallel group:** D

**What:** Schedule bot driving after every lifecycle transition that can hand control to a bot.
**Interface:** Call the idempotent scheduler after game creation, successful REST/WS mutations, timer-driven actions, and application restoration. Reuse existing mutation finalization and broadcast helpers rather than adding a parallel server protocol.
**Behavior:** Bot heroes become ready automatically so timed games do not remain in `WAITING_FOR_PLAYERS`. Bot search time counts as bot thinking time unless a later product decision changes it. Timeout actions and bot actions must not race into duplicate mutations. Automatic bot responses should freeze rollback under the same policy as other externally revealed decisions.
**Tests:** Cover creation-to-first-bot-action, human-to-bot handoff over REST and WebSocket, restored-game resumption, timed readiness, timeout races, rollback boundaries, one replay entry, and one broadcast per applied action.
**Validation:** `PYTHONPATH=src uv run pytest tests/server/ -q`

### Task 7: Expose Bot Game Creation

**Files (footprint):**
- Modify: `src/goa2/server/models.py`
- Modify: `src/goa2/server/routes_games.py`
- Modify: `docs/CLIENT_INTEGRATION_GUIDE.md`
- Modify: `tests/server/test_server_rest.py`

**Depends on:** Task 6
**Parallel group:** E

**What:** Add an optional bot configuration to normal game creation without changing response models.
**Interface:** Extend `CreateGameRequest` with an optional mapping from roster hero ID to `BotSpec` or an equivalent request model. Keep `CreateGameResponse` and token fields unchanged.
**Behavior:** Reject unknown heroes, duplicate/incompatible assignments, unsupported agent kinds, and unsafe ISMCTS settings with clear 4xx responses. Requests without bots must behave byte-for-byte as before. Document bot configuration, token behavior, supported kinds, and limitations. Draft-created games remain unsupported.
**Tests:** Cover no-bot compatibility, Random/Heuristic creation, malformed specifications, hero-not-in-roster, unsupported draft use, and unchanged response shape.
**Validation:** `PYTHONPATH=src uv run pytest tests/server/test_server_rest.py -q`

### Task 8: Bound ISMCTS For Live Use

**Files (footprint):**
- Modify: `src/automata/search/config.py`
- Modify: `src/goa2/server/bots.py`
- Modify: `src/goa2/server/bot_models.py`
- Modify: `tests/server/test_server_bots.py`
- Test: `tests/ai/test_ismcts.py`

**Depends on:** Task 3, Task 7
**Parallel group:** F

**What:** Make ISMCTS an explicit, resource-bounded server option rather than running the evaluation defaults on the event loop.
**Interface:** Add validated production limits for iterations and decision timeout. Protect searches with a process-wide asyncio semaphore and run them through `asyncio.to_thread()` using only cloned state.
**Behavior:** Never run search on the event-loop thread. On queue timeout, search timeout, invalid result, or agent exception, fall back to `HeuristicAgent`. A timed-out worker may finish in its thread but must retain no reference to mutable live state and its result must never apply later. Emit structured logs for latency, stale decisions, queueing, timeout, and fallback.
**Tests:** Cover semaphore serialization, event-loop responsiveness, timeout fallback, stale completion, upper-bound validation, and deterministic behavior under a fixed seed and budget.
**Validation:** `PYTHONPATH=src uv run pytest tests/ai/test_ismcts.py tests/server/test_server_bots.py -q`

### Task 9: End-To-End Verification And Documentation

**Files (footprint):**
- Modify: `docs/CLIENT_INTEGRATION_GUIDE.md`
- Modify: `docs/plan_ai_ladder.md`
- Modify: `tests/server/test_server_bots.py`

**Depends on:** Task 8
**Parallel group:** G

**What:** Verify complete automated play and record operational constraints.
**Interface:** Add end-to-end tests through the public creation API and normal server mutation paths; do not call coordinator internals for these scenarios.
**Behavior:** Demonstrate Random-vs-Random completion, Heuristic-vs-Random completion, human-vs-Heuristic handoff, restart during a pending bot decision, and bounded ISMCTS fallback. Document supported modes, performance expectations, and why draft bots remain excluded.
**Tests:** Assert legal game completion, persistence after every bot mutation, player-scoped visibility, replay integrity, WebSocket updates, and no orphan bot tasks after shutdown.
**Validation:** Run `PYTHONPATH=src uv run pytest tests/ -q`, `uv run ruff check src/ tests/`, and `uv run mypy src/`.

## Release Gates

1. **Internal bot gate:** Tasks 1-6 complete; Random and Heuristic bots can be enabled through `GameRegistry` tests but are not yet public API.
2. **Public bot gate:** Task 7 complete; clients can create Random and Heuristic bot games.
3. **Search bot gate:** Tasks 8-9 complete; ISMCTS is opt-in with strict resource limits and Heuristic fallback.

## Key Risks

- **Event-loop blocking:** All non-trivial policy computation must run outside the event loop.
- **Stale decisions:** Human actions, timers, disconnect handling, or another bot may advance state while computation runs; every result must be revalidated.
- **Duplicate scheduling:** REST, WebSocket, timers, restoration, and the bot worker itself can all request progress; one task per game and idempotent scheduling are mandatory.
- **Mixed-team search:** ISMCTS must anchor to the requested hero before it is safe for human/bot teammates.
- **Persistence drift:** Bot metadata must remain backward-compatible and be saved atomically with the game.
- **Hidden information:** Agents may inspect server state only through a cloned decision state; ISMCTS must continue determinizing hidden enemy commitments rather than treating them as known.
- **CPU saturation:** Thread offloading protects the event loop but does not eliminate GIL/CPU contention. Keep low production budgets and bounded concurrency; move to processes only if measured load requires it.
