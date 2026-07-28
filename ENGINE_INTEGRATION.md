# Engine Integration Notes — goa2-backend (adopted engine)

Status: **ADOPTED** as the game engine (Python). We build the **AI** (and optionally a
UI) on top. Licensing: author has given permission; an explicit LICENSE is to be added to
the upstream repo later (tracked risk, not a code blocker).

Upstream: https://github.com/PedroVIOliv/goa2-backend
Evaluated at commit ~2026-07-12. `uv run pytest tests/engine` → **2396 passed in ~9s**.

## Why we adopted it

It independently implements the architecture we concluded this game needs:
- **Deterministic**, stack-based resolver (`GameState.execution_stack`).
- **Serializable / resumable**: `GameState` is a Pydantic model; snapshots via
  `model_dump(mode="json")` (board excluded — it is static).
- **Server-owned hidden information** via `build_view(state, player_id)` (player-scoped).
- **Enumerated legal moves** at every decision point (see below) — no need to reimplement
  legality, targeting, combat math.
- **34 heroes** with real card-effect implementations (`src/goa2/data/heroes/`,
  `src/goa2/scripts/*_effects.py`) — the bulk of the content work, already done.
- Fast (2396 tests / ~9s) → good for search-based AI.

It has **no AI** — that is our contribution.

## The AI-facing API (in-process, NOT the REST server)

Search AIs (ISMCTS) need thousands of cheap clones/rollouts, so we call the engine
in-process via `GameSession`, never the HTTP/WebSocket server.

Key modules:
- `goa2.engine.setup.GameSetup.create_game(...)` — headless game creation (hero lists,
  teams, map).
- `goa2.engine.session.GameSession(state)` — orchestrator:
  - PLANNING: `commit_card(hero_id, card)`, `pass_turn(hero_id)`, `uncommit_card(...)`,
    `finish_planning(...)`. All heroes commit simultaneously (hidden), then resolution
    begins. Legal actions = the hero's hand (+ pass).
  - RESOLUTION/other: `advance(response=None)` → `SessionResult`.
- `SessionResult.result_type ∈ {INPUT_NEEDED, ACTION_COMPLETE, PHASE_CHANGED, GAME_OVER}`,
  plus `input_request`, `current_phase`, `winner`, `events`.
- `goa2.domain.input.InputRequest`:
  - `request_type` (SELECT_UNIT/SELECT_HEX/CHOOSE_ACTION/DEFENSE_CARD/…),
  - `player_id` — **whose decision it is (the info set owner)**,
  - `options: list[InputOption]` — **enumerated legal choices** (each `id` + `metadata`),
  - `can_skip` (+ `SKIP`/`DONE` sentinels) for optional/multi-select.
- `goa2.domain.input.InputResponse` — what we submit back via `advance(response)`.
- `goa2.domain.views.build_view(state, player_id)` — redacted, player-scoped state.

### The generic AI decision loop
```
session = GameSession(state)
while not game_over:
    if phase == PLANNING:
        for each hero we control: session.commit_card(hero, chosen_from_hand)
    else:
        result = session.advance(response)
        if result.result_type == INPUT_NEEDED:
            req = result.input_request         # who = req.player_id
            legal = req.options (+ SKIP if req.can_skip)   # enumerated moves
            response = agent.choose(view_for(req.player_id), req, legal)
        elif GAME_OVER: break
```
This gives a clean, engine-agnostic `Agent.choose(view, request, legal_options)` contract.

## ISMCTS feasibility

- **Clone**: `GameState.model_copy(deep=True)` (or dump/validate); share the static board
  to keep it cheap. Benchmark early.
- **Determinization**: from a player's `build_view`, randomize unknown info (opponent
  hands/decks) consistent with what is visible, then run perfect-info rollouts.
- **Simultaneous move**: PLANNING commits are simultaneous + hidden → model as a
  simultaneous decision node (decoupled UCB / regret matching), not sequential.
- **player_id** on every request tells us which information set a decision belongs to.

## What this supersedes from our earlier (TypeScript) work

- TS engine (geometry, board-index, RNG, schemas): superseded by the Python engine.
- Card OCR/review pipeline + `data/cards.json`: largely redundant (engine has hero/card
  data + effects). Possibly useful only to cross-validate their data.
- `board.json` + calibration tool: engine ships its own map(s) (`data/maps/`).
- **Kept**: our AI design thinking (ISMCTS, simultaneous-move analysis) — now the core.

## Open questions / to verify next

1. Clone cost benchmark (states/sec) → sets the MCTS iteration budget.
2. Exact `InputResponse` construction per `request_type` (map option → response).
3. How `create_game` selects the map / hero rosters for our Quick-Game target
   (Wasp, Xargatha / Arien, Brogan; 2v2 single lane).
4. Determinization hook: what `build_view` hides vs reveals, to sample legal worlds.

## Findings (as of the AI work)

- **Clone cost**: `GameState.model_copy(deep=True)` ≈ **3.4 ms** (~291/s);
  `model_dump(mode="json")` ≈ 0.9 ms. Too slow to clone-per-option at eval
  scale, so the heuristic uses static scoring. `automata.clone.clone_state`
  shares the static board geometry and copies only the mutable tiles/state →
  **~1.4 ms** (~700/s), verified independent (playing a clone forward leaves the
  original's positions + occupancy intact). This is the MCTS clone.
- **Input contract** (verified in `automata/`): `advance({"selection": <raw>})`;
  raw value comes from `InputOption.metadata` (`hex`/`raw`) else the option id.
  `UPGRADE_PHASE` is special: `player_id="simultaneous"`, per-hero options in
  `request.context["players"]`, selection = `{"hero_id","card_id"}` (card id from
  a colour group's `pair`), applied one per `advance()` until upgrades are empty.
- **Quick game**: `create_game(map, ["Wasp","Xargatha"], ["Arien","Brogan"],
  game_type="QUICK")` on `src/goa2/data/maps/forgotten_island.json`
  (lane `RedBase→RedBeach→Mid→BlueBeach→BlueBase`, start battle zone `Mid`).
- **Baselines** (eval harness, sides alternated): Random vs Random = 50%
  (20-20/40). The **greedy one-ply static heuristic is ~random-strength**
  (~40%, CI 30-51% over 120 games) — it wins some games decisively and loses
  others. Expected for one-ply scoring in an imperfect-information,
  simultaneous-move game: reliably beating random needs **lookahead (ISMCTS)**,
  which was the plan. `evaluate_state` + the eval harness are the reusable
  substrate for it.
