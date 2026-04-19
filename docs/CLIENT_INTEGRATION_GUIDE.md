# Client Integration Guide

This guide covers everything a frontend developer needs to connect to the GoA2 backend API.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication](#authentication)
3. [REST API Reference](#rest-api-reference)
4. [WebSocket Protocol](#websocket-protocol)
5. [Game Flow](#game-flow)
6. [Understanding the Game View](#understanding-the-game-view)
7. [Handling Input Requests](#handling-input-requests)
8. [Events](#events)
9. [Persistence & Reconnection](#persistence--reconnection)
10. [Error Handling](#error-handling)

---

## Quick Start

### 1. Start the server

```bash
PYTHONPATH=src uv run uvicorn goa2.server.app:create_app --factory --reload
```

The server runs on `http://localhost:8000` by default.

### 2. Create a game

```bash
curl -X POST http://localhost:8000/games \
  -H "Content-Type: application/json" \
  -d '{
    "map_name": "forgotten_island",
    "red_heroes": ["arien"],
    "blue_heroes": ["knight"]
  }'
```

Response:

```json
{
  "game_id": "a1b2c3d4e5f6",
  "player_tokens": [
    {"hero_id": "hero_arien", "token": "abc123..."},
    {"hero_id": "hero_knight", "token": "def456..."}
  ],
  "spectator_token": "ghi789..."
}
```

Save these tokens — they are the only way to authenticate.

### 3. Get the game view

```bash
curl http://localhost:8000/games/a1b2c3d4e5f6 \
  -H "Authorization: Bearer abc123..."
```

### 4. Connect via WebSocket

```
ws://localhost:8000/games/a1b2c3d4e5f6/ws?token=abc123...
```

On connection, the server immediately sends a `STATE_UPDATE` message with the current game view.

---

## Authentication

The server uses bearer tokens generated at game creation. There are no usernames, passwords, or sessions — tokens are the sole identity.

### Token types

| Type | Created per | Access level |
|------|-------------|-------------|
| Player token | Each hero in the game | Full: view own cards, commit cards, submit input |
| Spectator token | One per game | Read-only: view game state (no facedown cards visible) |

### REST authentication

Include the token in the `Authorization` header:

```
Authorization: Bearer <token>
```

All endpoints except `POST /games` and `GET /heroes` require authentication. The server validates that the token belongs to the game specified in the URL path.

### WebSocket authentication

Pass the token as a query parameter:

```
ws://host/games/{game_id}/ws?token=<token>
```

Invalid tokens are rejected with WebSocket close code `4001`. Tokens that don't match the game ID are rejected with close code `4003`.

---

## REST API Reference

### `GET /heroes`

List available hero IDs. No authentication required.

**Response:** `200 OK`

```json
["arien", "knight", "rogue"]
```

### `POST /games`

Create a new game. No authentication required.

**Request body:**

```json
{
  "map_name": "forgotten_island",
  "red_heroes": ["arien"],
  "blue_heroes": ["knight"],
  "cheats_enabled": false,
  "game_type": "LONG"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `map_name` | string | `"forgotten_island"` | Map to use (must exist in `data/maps/`) |
| `red_heroes` | string[] | required | Hero IDs for the red team |
| `blue_heroes` | string[] | required | Hero IDs for the blue team |
| `cheats_enabled` | boolean | `false` | Enable cheats for this game (unlocks gold cheat API) |
| `game_type` | string | `"LONG"` | `"QUICK"` or `"LONG"`. Controls wave and life counter setup (see below) |

**Game types:**

| Game Type | Players | Wave Counters | Life Counters |
|-----------|---------|---------------|---------------|
| `QUICK` | 4 | 3 | 4 |
| `QUICK` | 5 | 3 | 4 |
| `QUICK` | 6 | 3 | 5 |
| `LONG` | 4–5 | 5 | 6 |
| `LONG` | 6 | 5 | 8 |

Omitting `game_type` defaults to `"LONG"` (standard game).

**Response:** `201 Created`

```json
{
  "game_id": "a1b2c3d4e5f6",
  "player_tokens": [
    {"hero_id": "hero_arien", "token": "abc123..."},
    {"hero_id": "hero_knight", "token": "def456..."}
  ],
  "spectator_token": "ghi789..."
}
```

### `GET /games/{game_id}`

Get the current game view for the authenticated player.

**Response:** `200 OK`

```json
{
  "view": { ... },
  "input_request": null,
  "winner": "RED"
}
```

The `view` object contains the player-scoped game state (see [Understanding the Game View](#understanding-the-game-view)). The `input_request` is present when the server is waiting for this player's input.

The `winner` key is only present when game has ended (`view.phase === "GAME_OVER"`). Its value is `"RED"` or `"BLUE"`. Check for its presence with `response.get("winner")` rather than assuming it exists.

### `POST /games/{game_id}/cards`

Commit a card during the PLANNING phase.

**Request body:**

```json
{
  "card_id": "arien_tidal_wave_1"
}
```

**Response:** `200 OK` — returns `ActionResultResponse` (see below).

### `POST /games/{game_id}/pass`

Pass your turn during the PLANNING phase (the hero will not play a card this round).

**Request body:** empty

**Response:** `200 OK` — returns `ActionResultResponse`.

### `POST /games/{game_id}/input`

Submit a response to an input request (e.g., selecting a unit, choosing a hex).

**Request body:**

```json
{
  "request_id": "optional-id",
  "selection": "hero_knight"
}
```

The `selection` value depends on the input request type — it may be a string (unit ID), a hex dict (`{"q": 0, "r": 1, "s": -1}`), an integer, or a card ID.

**Response:** `200 OK` — returns `ActionResultResponse`.

### `POST /games/{game_id}/advance`

Advance the game state without submitting input. Used when the engine needs to continue processing (e.g., transitioning between phases).

**Request body:** empty

**Response:** `200 OK` — returns `ActionResultResponse`.

### `POST /games/{game_id}/rollback`

Rollback the current actor's resolution to the action choice step. Only the current actor can rollback, and only when `can_rollback` is `true` on the current `InputRequest`.

**Request body:** empty

**Response:** `200 OK` — returns `ActionResultResponse`. The `input_request` will be the action choice prompt again.

**Error conditions:**
- `400` — No active resolution or no rollback snapshot available
- `403` — Not the current actor, or spectator token used

**When rollback is disabled:** If another player was prompted during the current actor's resolution (e.g., for defense card selection), rollback is permanently disabled for that resolution. The `can_rollback` field on `InputRequest` will be `false`.

### `POST /games/{game_id}/cheats/gold`

Give gold to a hero (cheats must be enabled and game must be in PLANNING phase).

**Request body:**

```json
{
  "hero_id": "hero_arien",
  "amount": 5
}
```

| Field | Type | Description |
|-------|------|-------------|
| `hero_id` | string | ID of the hero to give gold to |
| `amount` | integer | Amount of gold to give (must be positive) |

**Response:** `200 OK` — returns `ActionResultResponse` with a `GOLD_GAINED` event.

**Error conditions:**
- `403` — Cheats not enabled for this game, spectator token used, or not in PLANNING phase
- `404` — Hero not found
- `400` — Amount is not a positive integer

### ActionResultResponse shape

All mutation endpoints return this shape:

```json
{
  "result_type": "INPUT_NEEDED",
  "current_phase": "RESOLUTION",
  "events": [
    {
      "event_type": "UNIT_MOVED",
      "actor_id": "hero_arien",
      "target_id": null,
      "from_hex": {"q": 0, "r": 0, "s": 0},
      "to_hex": {"q": 1, "r": -1, "s": 0},
      "metadata": {}
    }
  ],
  "input_request": {
    "type": "SELECT_HEX",
    "player_id": "hero_arien",
    "prompt": "Choose a hex to move to",
    "valid_hexes": [{"q": 1, "r": 0, "s": -1}]
  },
  "winner": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `result_type` | string | `INPUT_NEEDED`, `ACTION_COMPLETE`, `PHASE_CHANGED`, or `GAME_OVER` |
| `current_phase` | string | Current game phase (see [Game Flow](#game-flow)) |
| `events` | array | Game events emitted during this action (see [Events](#events)) |
| `input_request` | object/null | Present when `result_type` is `INPUT_NEEDED` |
| `winner` | string/null | `"RED"` or `"BLUE"` when `result_type` is `GAME_OVER` |

---

## WebSocket Protocol

### Connection

```
ws://host/games/{game_id}/ws?token=<bearer_token>
```

On successful connection, the server sends an initial `STATE_UPDATE` message with the full game view.

### Client-to-server messages

All messages are JSON with a `type` field:

#### `COMMIT_CARD`

```json
{
  "type": "COMMIT_CARD",
  "card_id": "arien_tidal_wave_1"
}
```

#### `PASS_TURN`

```json
{
  "type": "PASS_TURN"
}
```

#### `SUBMIT_INPUT`

```json
{
  "type": "SUBMIT_INPUT",
  "request_id": "",
  "selection": "hero_knight"
}
```

#### `GET_VIEW`

Request a fresh state update (available to both players and spectators):

```json
{
  "type": "GET_VIEW"
}
```

#### `ROLLBACK`

Rollback the current actor's resolution to the action choice. Only the current actor can send this, and only when `can_rollback` is `true` on the current input request.

```json
{
  "type": "ROLLBACK"
}
```

**Response:** `ACTION_RESULT` with the action choice input request.

#### `CHEATS_GOLD`

Give gold to a hero (cheats must be enabled and game must be in PLANNING phase):

```json
{
  "type": "CHEATS_GOLD",
  "hero_id": "hero_arien",
  "amount": 5
}
```

**Error responses:**
- `Cheats are not enabled for this game` — Cheats were not enabled at game creation
- `Expected phase PLANNING, but game is in RESOLUTION` — Gold cheat only works during PLANNING phase
- `Hero 'X' not found` — The specified hero_id does not exist
- `Amount must be a positive integer` — The amount must be > 0

### Server-to-client messages

#### `STATE_UPDATE`

Sent on connection, on `GET_VIEW` requests, and broadcast to all connected clients after any mutation:

```json
{
  "type": "STATE_UPDATE",
  "view": { ... },
  "input_request": { ... },
  "winner": "RED"
}
```

The `input_request` key is only present when there is a pending input request. Check for its presence with `msg.get("input_request")` rather than assuming it exists.

The `winner` key is only present when the game has ended (`view.phase === "GAME_OVER"`). Its value is `"RED"` or `"BLUE"`. Check for its presence with `msg.get("winner")` rather than assuming it exists.

#### `ACTION_RESULT`

Sent to the player who performed the action:

```json
{
  "type": "ACTION_RESULT",
  "result_type": "INPUT_NEEDED",
  "current_phase": "RESOLUTION",
  "events": [ ... ],
  "input_request": { ... },
  "winner": null
}
```

#### `ERROR`

```json
{
  "type": "ERROR",
  "detail": "Input expected from 'hero_knight', not 'hero_arien'"
}
```

### Broadcast behavior

After a mutation (`COMMIT_CARD`, `PASS_TURN`, `SUBMIT_INPUT`):

1. The acting player receives an `ACTION_RESULT` message
2. **All** connected clients (including the acting player) receive a `STATE_UPDATE` broadcast with their player-scoped view

This means the acting player gets both messages. The `ACTION_RESULT` contains events for animation, while `STATE_UPDATE` has the authoritative view to render.

### Spectator restrictions

Spectators can only send `GET_VIEW` messages. All other message types return an error:

```json
{"type": "ERROR", "detail": "Spectators can only GET_VIEW"}
```

---

## Game Flow

The game progresses through these phases:

```
PLANNING → REVELATION → RESOLUTION → CLEANUP → LEVEL_UP → PLANNING
                                                     ↓
                                                 GAME_OVER
```

### Phase descriptions

| Phase | Description | Client action |
|-------|-------------|---------------|
| `PLANNING` | Each player selects a card to commit (or passes). | Call `commit_card` or `pass_turn` for each hero. Once all heroes have committed/passed, the phase transitions automatically. |
| `REVELATION` | Cards are revealed (flipped faceup). | Call `advance` to progress. No player input needed. |
| `RESOLUTION` | Heroes act in initiative order. The engine pauses for input requests (selecting targets, movement hexes, etc.). | Respond to `input_request`s via `submit_input`. Call `advance` when `result_type` is `ACTION_COMPLETE` or `PHASE_CHANGED` to continue. |
| `CLEANUP` | Round-end bookkeeping (discard cards, reset effects). | Call `advance` to progress. |
| `LEVEL_UP` | Heroes upgrade cards if they've earned enough gold. May require input for upgrade choices. | Respond to any `input_request`s, then `advance`. |
| `GAME_OVER` | A team's life counters have reached 0. | Check the `winner` field. |

### Typical client loop

```
1. Check result_type from last response
2. If INPUT_NEEDED → render input_request options, wait for player choice, submit_input
3. If ACTION_COMPLETE → call advance to continue (REST only — see note)
4. If PHASE_CHANGED → update phase UI, call advance to continue
5. If GAME_OVER → show winner
```

**Note:** The `advance` action is only available via REST (`POST /games/{game_id}/advance`). There is no WebSocket equivalent. WebSocket-only clients can use `SUBMIT_INPUT` for input responses and `COMMIT_CARD`/`PASS_TURN` for planning, but must use REST for advance calls.

---

## Understanding the Game View

The `view` object returned by `GET /games/{game_id}` and WebSocket `STATE_UPDATE` messages has this structure:

```json
{
  "phase": "PLANNING",
  "round": 1,
  "turn": 1,
  "current_actor_id": null,
  "unresolved_hero_ids": ["hero_arien", "hero_knight"],
  "unresolved_cards": [
    { "hero_id": "hero_arien", "initiative": 7, "card": { ... } },
    { "hero_id": "hero_knight", "initiative": 5, "card": { ... } }
  ],
  "active_zone_id": null,
  "cheats_enabled": false,
  "tie_breaker_team": "RED",
  "teams": {
    "RED": { ... },
    "BLUE": { ... }
  },
  "board": {
    "tiles": { ... },
    "zones": { ... },
    "entity_locations": { ... }
  },
  "effects": [ ... ],
  "markers": { ... },
  "tokens": [ ... ]
}
```

### Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `phase` | string | Current game phase |
| `round` | int | Current round number (starts at 1) |
| `turn` | int | Current turn within the round |
| `current_actor_id` | string/null | Hero currently acting during RESOLUTION |
| `unresolved_hero_ids` | string[] | Heroes that haven't acted yet this round |
| `unresolved_cards` | object[] | Cards in resolution order (highest initiative first). Each entry: `{hero_id, initiative, card}`. Only populated during RESOLUTION phase; empty array otherwise. Ties broken by `tie_breaker_team`. Recalculated dynamically — order may change between actions due to modifiers. |
| `active_zone_id` | string/null | Currently active zone (if applicable) |
| `cheats_enabled` | boolean | Whether cheats are enabled for this game |
| `tie_breaker_team` | string | Team that currently wins ties (`"RED"` or `"BLUE"`) |
| `tokens` | object[] | Tokens currently on the board (see [Tokens](#tokens)) |

### Team data

Each team contains:

```json
{
  "color": "RED",
  "life_counters": 4,
  "heroes": [ ... ],
  "minions": [ ... ]
}
```

### Hero data

```json
{
  "id": "hero_arien",
  "name": "Arien",
  "title": "Tideshaper",
  "team": "RED",
  "level": 1,
  "gold": 0,
  "items": [],
  "hand": [ ... ],
  "deck": [ ... ],
  "played_cards": [ ... ],
  "current_turn_card": null,
  "discard_pile": [ ... ],
  "ultimate_card": null
}
```

**Important:** `played_cards` is a fixed-position array where:
- Turn 1 card → `played_cards[0]`
- Turn 2 card → `played_cards[1]`
- Turn 3 card → `played_cards[2]`
- etc.

When a card is removed (discarded, returned to hand, etc.), its position becomes `null` but subsequent cards fill their correct turn-based positions:

```json
"played_cards": [
  { "id": "card_1", ... },  // Turn 1 card (position 0)
  null,                        // Turn 2 card was removed
  { "id": "card_3", ... },  // Turn 3 card (position 2, not 1)
  { "id": "card_4", ... }   // Turn 4 card (position 3)
]
```

Positions reset to empty at the start of each round.

### Card visibility rules

The view is player-scoped — what you see depends on your token:

- **Your hero's cards:** Full details visible for all cards (hand, deck, played, current turn card, ultimate)
- **Other heroes' FACEUP cards:** Full details visible (id, name, tier, action, is_ranged, range_value, radius_value, etc.)
- **Other heroes' FACEDOWN cards:** Partial details - hides `id`, `name`, `is_ranged`, `range_value`, `radius_value`. Shows `tier`, `color`, `primary_action`, `primary_action_value`, `secondary_actions`, `effect_id`, `effect_text`, `initiative`, `state`, `is_facedown`, `item`, `is_active`
- **Other heroes' hand:** Empty array `[]` (no cards visible at all in hand)
- **Deck of other heroes:** Shows `{"count": N}` instead of card details
- **Discard piles:** Always fully visible (public information)

### Board structure

```json
{
  "tiles": {
    "0_0_0": {
      "hex": {"q": 0, "r": 0, "s": 0},
      "zone_id": "zone_center",
      "is_terrain": false,
      "occupant_id": "hero_arien",
      "spawn_point": null
    }
  },
  "zones": {
    "zone_center": {
      "id": "zone_center",
      "neighbors": ["zone_north", "zone_south"],
      "spawn_points": [ ... ]
    }
  },
  "entity_locations": {
    "hero_arien": {"q": 0, "r": 0, "s": 0},
    "hero_knight": {"q": 2, "r": -1, "s": -1}
  }
}
```

Hex coordinates use the cube coordinate system: `q + r + s = 0`.

`entity_locations` is the authoritative source for unit positions.

### Minion data

```json
{
  "id": "minion_1",
  "type": "MELEE",
  "team": "RED",
  "value": 2,
  "is_heavy": false
}
```

Minion types: `MELEE` (value 2), `RANGED` (value 2), `HEAVY` (value 4).

### Effects

Active area effects on the board:

```json
{
  "id": "effect_1",
  "type": "BUFF",
  "source_card_id": "arien_tidal_wave_1",
  "duration": "UNTIL_END_OF_ROUND",
  "is_active": true,
  "scope": {
    "shape": "SINGLE",
    "range": 0,
    "origin_id": null,
    "origin": {"q": 0, "r": 0, "s": 0},
    "affects": "ALLIES"
  },
  "stat_type": "ATTACK",
  "stat_value": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique effect ID |
| `type` | string | Effect type (e.g. `"los_blocker"`, `"placement_prevention"`, `"area_stat_modifier"`) |
| `source_card_id` | string/null | Card that created this effect. `null` for token-bound effects |
| `duration` | string | `"THIS_TURN"`, `"THIS_ROUND"`, `"PASSIVE"`, or `"NEXT_TURN"` |
| `is_active` | boolean | Whether the effect is currently active |
| `scope.shape` | string | `"point"`, `"radius"`, `"adjacent"`, `"line"`, `"zone"`, `"global"` |
| `scope.range` | int | Range for radius/line shapes |
| `scope.origin_id` | string/null | Entity ID the effect is anchored to (e.g. a token ID). Look up in `entity_locations` for position |
| `scope.origin` | hex/null | Fixed hex origin (overrides `origin_id` when present) |
| `scope.affects` | string | Who is affected (e.g. `"all_units"`, `"enemy_heroes"`) |
| `stat_type` | string/null | For stat modifier effects |
| `stat_value` | int | Modifier amount |

**Token-bound effects:** When `source_card_id` is `null` and `scope.origin_id` points to a token, the effect's lifecycle is tied to the token — it persists as long as the token is on the board and is automatically removed when the token is removed.

### Tokens

Tokens are board objects (obstacles, traps, bombs, etc.) that are distinct from units. They appear in the `tokens` array and in `entity_locations`.

```json
{
  "id": "smoke_bomb_1",
  "name": "Smoke Bomb",
  "token_type": "smoke_bomb",
  "owner_id": "hero_min",
  "is_passable": false,
  "is_facedown": false,
  "hex": {"q": 1, "r": -1, "s": 0}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique token ID (also appears in `entity_locations` and tile `occupant_id`) |
| `name` | string | Display name |
| `token_type` | string | Token type: `"smoke_bomb"`, `"grenade"`, `"mine_blast"`, `"mine_dud"`. For facedown enemy tokens, this is `"mine"` (true type hidden) |
| `owner_id` | string/null | Hero ID that owns/placed this token |
| `is_passable` | boolean | If `true`, units can move through this token but not land on it. Mine tokens are passable |
| `is_facedown` | boolean | If `true`, the token's actual type is hidden from opponents. The owning team sees the real `token_type`; opponents see `"mine"` |
| `hex` | hex/null | Current position on the board. `null` if the token exists but is not placed |

Tokens are obstacles — any tile with a token as `occupant_id` is impassable unless the token is **passable** (e.g. mines). Passable tokens can be traversed but not landed on. When an enemy hero moves through a passable mine token, the mine is triggered and removed. Blast mines (`mine_blast`) force the moved hero to discard a card; dud mines (`mine_dud`) have no effect.

When a token is removed from the board, any effects anchored to it (via `scope.origin_id`) are automatically removed.

#### Mine path choice

When an enemy hero's movement path passes through mines and multiple routes with different mine combinations exist, the player controlling the movement receives a `SELECT_OPTION` input request to choose which path to take. Each option includes:

```json
{
  "id": "0",
  "text": "Path through 1 mine(s)",
  "metadata": {
    "mine_count": 1,
    "mine_hexes": [{"q": 1, "r": -1, "s": 0}],
    "path": [
      {"q": 0, "r": 0, "s": 0},
      {"q": 1, "r": -1, "s": 0},
      {"q": 2, "r": -1, "s": -1}
    ]
  }
}
```

- `id`: numeric index of the path option (opaque — do not parse)
- `mine_count`: number of mines on this path
- `mine_hexes`: hex positions of the mines
- `path`: full sequence of hexes from start to destination

The path choice is made by the **current actor** (the player controlling the movement), not necessarily the hero being moved (relevant for forced movement effects).

### Markers

```json
{
  "STUN": {
    "target_id": "hero_knight",
    "value": 1,
    "source_id": "hero_arien"
  }
}
```

---

## Handling Input Requests

When the engine needs player input, the response contains an `input_request` object.

### Input request shape

```json
{
  "type": "SELECT_HEX",
  "player_id": "hero_arien",
  "prompt": "Choose a hex to move to",
  "valid_hexes": [
    {"q": 1, "r": 0, "s": -1},
    {"q": 0, "r": 1, "s": -1}
  ]
}
```

The `type` field determines what kind of input is needed and what options fields are present.

### Common input request types

| Type | Options field | Selection value | Description |
|------|--------------|-----------------|-------------|
| `SELECT_HEX` | `valid_hexes` | `{"q": 1, "r": 0, "s": -1}` | Choose a hex on the board |
| `SELECT_UNIT` | `valid_options` | `"hero_knight"` | Choose a unit by ID |
| `SELECT_CARD` | `valid_options` | `"card_id"` | Choose a card by ID |
| `CHOOSE_ACTION` | `options` (list of `{id, text}`) | `"ATTACK"` | Choose from named actions |
| `SELECT_OPTION` | `options` (list of `{id, text}`) | `"option_id"` | Choose from generic options |
| `SELECT_CARD_OR_PASS` | `options` (list of `{id, text, ...}`) | `"card_id"` or `"PASS"` | Choose a defense card in reaction. Includes combat context fields and per-card metadata (see below) |
| `CHOOSE_ACTOR` | `player_ids` | `"hero_arien"` | Choose which hero acts next |
| `UPGRADE_PHASE` | `players` (special structure) | upgrade selection | Choose card upgrades |
| `CONFIRM_PASSIVE` | `options` (`["YES", "NO"]`) | `"YES"` or `"NO"` | Confirm a passive ability |

### How to respond

**Via REST:**

```bash
curl -X POST http://localhost:8000/games/{game_id}/input \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"selection": {"q": 1, "r": 0, "s": -1}}'
```

**Via WebSocket:**

```json
{
  "type": "SUBMIT_INPUT",
  "selection": {"q": 1, "r": 0, "s": -1}
}
```

The `selection` value must be one of the valid options provided in the input request. For hex selections, send the hex dict. For unit/card selections, send the ID string.

### Skippable inputs

If `can_skip` is `true` in the input request, the player can skip by submitting `null` as the selection:

```json
{"selection": null}
```

### Rollback

If `can_rollback` is `true` in the input request, the client should show a rollback button. When clicked, send a `POST /games/{game_id}/rollback` request (REST) or a `{"type": "ROLLBACK"}` message (WebSocket). This restores the game state to the action choice moment so the player can choose a different action.

Rollback is automatically disabled when another player is prompted during the current actor's turn (e.g., defense card selection). This prevents abuse of information gained from opponent choices. When rollback is disabled, the confirmation step at the end of resolution is also skipped.

### Defense card context

When a `SELECT_CARD_OR_PASS` input request is sent for defense, it includes additional combat context fields so the client can display attack/defense information to the player:

```json
{
  "type": "SELECT_CARD_OR_PASS",
  "player_id": "hero_knight",
  "prompt": "Player hero_knight, select a Defense card. Attack: 3, Defense needed: 2 (minion mod: +1)",
  "options": [
    {
      "id": "knight_shield_wall_1",
      "text": "Shield Wall (Def: 3)",
      "defense_value": 3,
      "base_defense": 2
    },
    {"id": "PASS", "text": "PASS"}
  ],
  "attack_value": 3,
  "minion_modifier": 1,
  "defense_needed": 2
}
```

**Top-level combat context fields:**

| Field | Type | Description |
|-------|------|-------------|
| `attack_value` | int \| null | The incoming attack's damage value |
| `minion_modifier` | int | Defense bonus from adjacent friendly minions |
| `defense_needed` | int \| null | Minimum card defense value to block (`attack_value - minion_modifier`) |

**Per-card option fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Card ID (or `"PASS"`) |
| `text` | string | Display text for the option |
| `defense_value` | int | Total computed defense (base + items + modifiers). Only on card options, not `"PASS"`. |
| `base_defense` | int | Card's base defense stat before modifiers. Only on card options, not `"PASS"`. |

The `"PASS"` option is always available — submit `"PASS"` if the player chooses not to defend.

---

## Events

Events describe what happened during a game action. They are meant for animation, logging, and replay — they don't change what's displayed (the view does that), but they tell you *how* it changed.

### Event structure

```json
{
  "event_type": "UNIT_MOVED",
  "actor_id": "hero_arien",
  "target_id": null,
  "from_hex": {"q": 0, "r": 0, "s": 0},
  "to_hex": {"q": 1, "r": -1, "s": 0},
  "metadata": {}
}
```

### Event types

| Event Type | Description | Key fields |
|------------|-------------|------------|
| `UNIT_MOVED` | A unit walked to a new hex | `actor_id`, `from_hex`, `to_hex` |
| `TOKEN_MOVED` | A token moved to a new hex | `target_id`, `from_hex`, `to_hex` |
| `UNIT_PLACED` | A unit was placed on the board (spawn, summon) | `actor_id`, `to_hex` |
| `TOKEN_PLACED` | A token was placed on the board | `actor_id`, `target_id`, `to_hex` |
| `UNIT_PUSHED` | A unit was forcibly moved | `actor_id`, `from_hex`, `to_hex` |
| `TOKEN_PUSHED` | A token was forcibly moved | `actor_id`, `target_id`, `from_hex`, `to_hex` |
| `UNITS_SWAPPED` | Two units exchanged positions | `actor_id`, `target_id`, `from_hex`, `to_hex` |
| `COMBAT_RESOLVED` | An attack was resolved | `actor_id`, `target_id`, `metadata` (combat details) |
| `UNIT_DEFEATED` | A unit was defeated | `actor_id` (defeated unit) |
| `UNIT_REMOVED` | A unit was removed from the board | `actor_id` |
| `TOKEN_REMOVED` | A token was removed from the board | `target_id`, `from_hex` |
| `MINE_TRIGGERED` | A mine token was triggered by hero movement | `actor_id` (current actor), `target_id` (mine ID), `from_hex`, `metadata.token_type`, `metadata.is_blast` |
| `EFFECT_CREATED` | A new area effect was placed | `metadata` (effect details) |
| `MARKER_PLACED` | A marker was placed on a unit | `target_id`, `metadata` |
| `MARKER_REMOVED` | A marker was removed | `target_id`, `metadata` |
| `GOLD_GAINED` | A hero gained gold | `actor_id`, `metadata.amount` |
| `LIFE_COUNTER_CHANGED` | A team's life counter changed | `metadata.team`, `metadata.amount` |
| `TURN_ENDED` | A hero's turn ended | `actor_id` |
| `GAME_OVER` | The game ended | `metadata.winner` |

### Using events for animation

Process events in order to build an animation sequence:

```
1. Receive ACTION_RESULT with events
2. For each event:
   - UNIT_MOVED → animate unit sliding from from_hex to to_hex
   - COMBAT_RESOLVED → show attack animation
   - UNIT_DEFEATED → show defeat animation
   - etc.
3. After animation, apply the STATE_UPDATE view as the final state
```

The events list may be empty if no observable state changes occurred (e.g., a phase transition with no actions).

---

## Persistence & Reconnection

### Auto-save behavior

The server automatically saves game state to disk after every mutation:
- Card commits, pass turns, input submissions, and advance calls all trigger a save
- Saves use atomic writes (temp file + rename) to prevent corruption
- Save directory defaults to `data/games/`, configurable via `GOA2_SAVE_DIR` environment variable

### Reconnection

Games survive server restarts. When the server starts, it restores all saved games from disk.

To reconnect after a server restart:
1. Use the same tokens you received at game creation
2. Call `GET /games/{game_id}` or connect via WebSocket — you'll get the current game state
3. If there's a pending `input_request`, continue responding to it normally

Tokens are not rotated on restart — the original tokens remain valid for the lifetime of the game.

### Limitations

- Games are stored in-memory with file-based persistence — there is no database
- If the save file is deleted while the server is running, the game continues in memory but won't survive a restart

---

## Error Handling

### HTTP status codes

| Status | Meaning | Example |
|--------|---------|---------|
| `201` | Game created | `POST /games` success |
| `200` | Success | All other successful responses |
| `400` | Bad request | Invalid input value |
| `401` | Unauthorized | Missing or invalid bearer token |
| `403` | Forbidden | Spectator trying to mutate, token doesn't match game, not your turn |
| `404` | Not found | Game ID doesn't exist, map not found, card not in hand |
| `409` | Conflict | Wrong game phase for the operation |

### Error response shape

```json
{
  "detail": "Expected phase PLANNING, but game is in RESOLUTION"
}
```

### WebSocket errors

WebSocket errors are sent as messages (the connection stays open):

```json
{
  "type": "ERROR",
  "detail": "Input expected from 'hero_knight', not 'hero_arien'"
}
```

Connection-level errors close the WebSocket with a code:

| Code | Reason |
|------|--------|
| `4001` | Invalid token |
| `4003` | Token does not match game |
| `4004` | Game not found |

### Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `"Missing or invalid Authorization header"` | No `Bearer` prefix or missing header | Add `Authorization: Bearer <token>` header |
| `"Invalid token"` | Token doesn't match any game | Use a token from `POST /games` response |
| `"Token does not match this game"` | Token belongs to a different game | Check the game_id in the URL |
| `"Expected phase PLANNING, but game is in RESOLUTION"` | Called commit_card/pass during wrong phase | Check `current_phase` before acting |
| `"Input expected from 'X', not 'Y'"` | Wrong player submitting input | Only the `player_id` from `input_request` should submit |
| `"Spectators cannot commit cards"` | Spectator token used for a mutation | Use a player token instead |
| `"Card 'X' not in Y's hand"` | Invalid card_id for commit | Check the hero's `hand` in the view |
