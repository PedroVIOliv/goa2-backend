# Character Draft Lobby — Design

**Date:** 2026-06-25
**Status:** Approved design (pre-implementation)

## Goal

Add an alternative game-start flow. Instead of one player choosing all heroes for both
teams up front, a host opens a **draft lobby** and shares a link. Friends join, pick (or are
randomized into) teams, a per-team **captain** drafts heroes through a **ban/pick sequence**,
players then **claim** which drafted hero they will play, and finally the existing game is
created from the result.

The drafting flow must be **pluggable** so future modes can change the hero pool and the
order of bans/picks per team.

## Key Decisions

| Decision | Choice |
|---|---|
| Pilot draft mode | Sequential ban/pick (Captain's-mode style) |
| Who drafts | A per-team **captain** makes all bans and picks |
| Hero → player binding | Players **claim** a drafted hero after the draft (CLAIMING phase) |
| Joining | Shared join link (carries `draft_id`) + display name → per-player token |
| Team assignment | Players self-select **or** host randomizes |
| Captains | Default = first joiner per team; **host can reassign** before start |
| Persistence | **In-memory only** (drafts are short-lived; no disk save/restore) |
| Real-time updates | Polling `GET /drafts/{id}` now; WebSocket broadcast is a **follow-on** |

## Architecture

A draft is **not** a `GameState`: it has no board, no placed heroes, and no execution stack.
It is a standalone pre-game subsystem that produces `red_heroes` / `blue_heroes` lists and
then hands them to the **unchanged** `GameSetup.create_game(...)`.

```
LOBBY ─► DRAFTING ─► CLAIMING ─► COMPLETE ──► GameSetup.create_game(red_heroes, blue_heroes, …)
                                              └─► existing GameRegistry game + per-hero tokens
```

### Modules

**Pure logic — new package `src/goa2/draft/` (framework-free, unit-testable):**

- `models.py` — `DraftState`, `DraftPlayer`, `DraftStep`, and the `DraftStatus` /
  `DraftActionType` / `PlayerRole` enums (Pydantic V2 models).
- `modes.py` — the `DraftMode` abstraction, a `DRAFT_MODES` registry keyed by name, and the
  built-in `SequentialBanPickMode`.
- `service.py` — pure transition functions operating on a `DraftState`:
  `join`, `set_team`, `randomize_teams`, `set_captain`, `start_draft`, `apply_action`,
  `claim_hero`, and `is_ready_to_create_game`. These raise typed errors on invalid input
  and never touch HTTP or the registry.

**Server layer:**

- `server/draft_registry.py` — in-memory `DraftRegistry` mapping `draft_id → ManagedDraft`
  (holds the `DraftState`, token→player_id map, host token, `asyncio.Lock`, and the
  resulting `game_id` once created). No disk persistence.
- `server/routes_draft.py` — REST endpoints under `/drafts`.
- `server/models.py` — request/response models for the new endpoints (additive only).
- `server/app.py` — register the new router and attach a `DraftRegistry` to `app.state`.

### Why a separate subsystem (vs. an engine `DRAFT` phase)

`GameState` construction requires a map, teams with instantiated heroes, spawn placement,
and token pools — none of which exist during a draft. The step engine's input contract is
also per-hero-turn, whereas a draft is a sequence of captain decisions. Keeping the draft
out of the engine keeps both systems simple and avoids polluting `GameState`/`build_view`.

## Data Models (`src/goa2/draft/models.py`)

```python
class DraftStatus(str, Enum):
    LOBBY = "LOBBY"
    DRAFTING = "DRAFTING"
    CLAIMING = "CLAIMING"
    COMPLETE = "COMPLETE"

class DraftActionType(str, Enum):
    BAN = "BAN"
    PICK = "PICK"

class DraftPlayer(BaseModel):
    id: str                      # draft-scoped, e.g. "p1"
    display_name: str
    team: TeamColor | None = None
    is_host: bool = False
    is_captain: bool = False
    claimed_hero: str | None = None   # set during CLAIMING

class DraftStep(BaseModel):
    index: int
    action: DraftActionType
    team: TeamColor

class DraftState(BaseModel):
    draft_id: str
    status: DraftStatus = DraftStatus.LOBBY
    map_name: str
    game_type: str               # "QUICK" | "LONG"
    draft_mode: str              # registry key, e.g. "sequential_ban_pick"
    red_size: int
    blue_size: int
    players: list[DraftPlayer] = []
    hero_pool: list[str] = []    # resolved at start from the mode
    sequence: list[DraftStep] = []   # resolved at start
    current_index: int = 0
    bans: dict[TeamColor, list[str]] = {}
    picks: dict[TeamColor, list[str]] = {}   # heroes drafted, team-level
    first_team: TeamColor | None = None
    game_id: str | None = None   # set on COMPLETE
    created_at: float
```

Server-side token data (token → player_id, host token) lives in `ManagedDraft`, **not** in
`DraftState`, so the public view never leaks tokens.

## Draft Mode Abstraction (`src/goa2/draft/modes.py`)

```python
class DraftMode(ABC):
    name: str
    description: str
    def hero_pool(self, all_heroes: list[str]) -> list[str]: ...
    def build_sequence(self, red_size: int, blue_size: int,
                       first_team: TeamColor) -> list[DraftStep]: ...

DRAFT_MODES: dict[str, DraftMode]   # registry, exposed via GET /drafts/modes
```

`SequentialBanPickMode` (pilot): full `HeroRegistry` pool; sequence = a configurable number
of alternating **bans** (default 1 per team, starting with `first_team`), followed by
alternating **picks** until each team has `team_size` heroes. A pick step is skipped/omitted
beyond a team's size when team sizes are uneven.

## Lifecycle & Endpoints (`/drafts`)

All player-facing endpoints authenticate with a **draft player bearer token**. Host-only
endpoints additionally require the token to be the host/admin token. A read-only spectator
token is issued at creation for shared viewing.

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /drafts/modes` | none | List available draft modes (name + description) |
| `POST /drafts` | none | Create lobby. Body: `map_name, game_type, draft_mode, red_size, blue_size, host_name`. Returns `draft_id`, host `player_token`, `spectator_token`. Host becomes player 1. |
| `POST /drafts/{id}/join` | none (link) | Body: `{display_name}`. Adds a player, returns `{player_id, player_token}`. Rejected if lobby full or not in LOBBY. |
| `GET /drafts/{id}` | player/spectator | Public draft view (+ caller identity; if COMPLETE and caller is a player who claimed, includes their `game_token`). |
| `POST /drafts/{id}/team` | player | Body `{team}`. Self-select RED/BLUE. LOBBY only; respects team size. |
| `POST /drafts/{id}/randomize-teams` | host | Shuffle all players into teams (sizes honored); resets captains to first-in-team. LOBBY only. |
| `POST /drafts/{id}/captain` | host | Body `{player_id}`. Designate that player's-team captain. LOBBY only. |
| `POST /drafts/{id}/start` | host | Validate teams full + captains set, resolve `hero_pool`/`sequence`, coin-flip `first_team`, → DRAFTING. |
| `POST /drafts/{id}/action` | acting captain | Body `{hero}`. BAN or PICK per current step. Advances `current_index`; when sequence ends → CLAIMING. |
| `POST /drafts/{id}/claim` | player | Body `{hero}`. Claim one of your team's drafted, unclaimed heroes. When all players have claimed → create game → COMPLETE. |

### Completion → game creation

When the last player claims, `service.is_ready_to_create_game` is true. The route builds
`red_heroes` / `blue_heroes` from each team's players in claim order, calls
`GameSetup.create_game(map_path, red_heroes, blue_heroes, cheats, game_type, seed)`,
registers the game in the existing `GameRegistry`, stores `game_id` on the draft, and maps
each draft player → their hero's game bearer token. The draft view (scoped to a player's
token) then exposes `game_id` + that player's `game_token`, so clients transition into the
existing game flow with no changes to the game endpoints.

## Validation & Errors

New typed exceptions in `server/errors.py` (subclassing the existing pattern, mapped to HTTP
4xx): `DraftNotFoundError` (404), `DraftFullError` (409), `NotHostError` (403),
`NotActingCaptainError` (403), `InvalidDraftPhaseError` (409), `HeroUnavailableError` (409),
`HeroNotClaimableError` (409), `InvalidTeamError` (400). The pure `service.py` raises its own
`DraftError` subclasses; routes translate them to HTTP errors.

Guards include: hero must be in pool and not banned/picked; action only by the acting team's
captain on the correct step; team selection respects `red_size`/`blue_size`; claim only from
your own team's drafted heroes and only once; host-only actions reject non-host tokens.

## Testing

Pure-logic tests (`tests/draft/test_draft_service.py`, `test_draft_modes.py`): join/team/
randomize/captain transitions, full sequential ban/pick walkthrough for 2v2 and uneven
sizes, claim flow, and every validation error. Mode tests assert sequence shape and pool.

Server tests (`tests/server/test_draft_rest.py`): end-to-end happy path (create → join →
teams → start → bans/picks → claim → game created with valid per-player game tokens that work
against existing `/games/{id}` endpoints), plus auth/permission failures (non-host start,
wrong-captain action, spectator write attempts). Run with
`PYTHONPATH=src uv run pytest tests/draft/ tests/server/ -q`.

## Client Contract

This is **additive** — no existing `/games`, `server/models.py` game shapes, `domain/input.py`,
`domain/events.py`, or `domain/views.py` contracts change. New endpoints, request/response
shapes, the `player_id`/token formats, and the lifecycle are documented in a new
**"Character Draft" section of `docs/CLIENT_INTEGRATION_GUIDE.md`**.

## Out of Scope (this build)

- Draft WebSocket / live push (follow-on; polling only for now).
- Disk persistence / restart survival for drafts.
- Additional draft modes beyond `SequentialBanPickMode` (the abstraction supports them).
- Reconnect/kick/lobby-chat niceties.
