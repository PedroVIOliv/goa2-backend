# Double-Lane Map Preparation

Status of the work for supporting the 8–10 player double-lane map.
The data model, push machinery, map loading, and **endgame rules** are now
fully lane-aware, and a real two-lane map exists
(`src/goa2/data/maps/across_the_river.json`). What remains is the 8–10
player setup config and frontend rendering (see "Still TBD" below).

Rules background (double-lane): two independent Lanes, each with its own
Battle Zone, minions, and Wave counter set. Minions are bound to the Battle
Zone they originally spawned in. Battles resolve separately but
simultaneously. Card text reading "the Battle Zone" is treated as
"a Battle Zone". The last-wave endgame compares total zones between each
Throne and *both* Battle Zones, with a tie meaning "undo the push and keep
playing".

## What was done

### Lane-aware data model (with legacy back-compat)

| Old (single-lane) | New (lane-aware) | Where |
|---|---|---|
| `Board.lane: list[str]` | `Board.lanes: dict[lane_id, list[str]]` | `domain/board.py` |
| `GameState.active_zone_id: str \| None` | `GameState.battle_zones: dict[lane_id, zone_id]` | `domain/state.py` |
| `GameState.wave_counter: int` | `GameState.wave_counters: dict[lane_id, int]` | `domain/state.py` |

- `DEFAULT_LANE_ID = "lane_1"` (`domain/board.py`) is the lane id of every
  single-lane game.
- The old names still work as **properties with setters** so existing tests,
  tools, and single-lane code keep functioning — but they **raise
  `RuntimeError` when the game has more than one lane**. This is deliberate:
  a missed call site fails loudly on a double-lane game instead of silently
  operating on the wrong lane.
- **Old save files load correctly**: `mode="before"` validators migrate
  `lane` → `lanes` and `active_zone_id`/`wave_counter` →
  `battle_zones`/`wave_counters`. Map JSON with a top-level `"lane"` key also
  still loads (the `map_loader.py` path goes through the same migration).

New lane helpers on `GameState`:

- `battle_zone_ids() -> set[str]` — zone ids of all current Battle Zones
  (what filters should use for "a Battle Zone").
- `battle_zone_for_lane(lane_id) -> str | None`
- `lane_of_zone(zone_id) -> str | None` (also on `Board.lane_of_zone`)

### Minion lane binding

- `Minion.lane_id: str` (default `"lane_1"`) records which lane a minion is
  bound to, per the respawn rule. `EntityFactory.create_minion()` takes an
  optional `lane_id`, and `GameSetup._spawn_initial_minions()` binds initial
  minions to their lane.
- Respawn candidate selection (`RespawnMinionStep`, `LanePushStep`) only
  picks limbo minions bound to the pushing/respawning lane.
- `ReturnMinionToZoneStep` ("Minions Outside of the Battle Zone") returns
  each stray minion to **its own lane's** Battle Zone.
- Heavy minion immunity (`engine/rules.py:is_immune`) checks friendly
  non-heavy minions in the heavy's **own lane's** Battle Zone, ignoring
  minions bound to other lanes.
- Displaced minions during a push (`ResolveDisplacementStep`) are placed in
  the Battle Zone of their own lane.

### Lane-scoped push machinery

- `CheckLanePushStep(lane_id=None)` — default checks **every** lane, so all
  existing call sites (end-of-turn, end-of-round, effect scripts like Min
  and Tigerclaw) are already multi-lane correct. Pass a `lane_id` to scope.
- `LanePushStep(lane_id=...)` — decrements that lane's Wave counter, moves
  that lane's Battle Zone, wipes/respawns only that lane's minions.
- `MinionBattleStep(lane_id=None)` — default resolves the minion battle for
  every lane ("separately, but simultaneously").
- `map_logic.get_push_target_zone_id(state, losing_team, lane_id=...)`.
- All new step fields have defaults, so step serialization round-trips and
  old persisted stacks load fine.

### Filters and effects

- `BattleZoneFilter` and `AdjacentToSpawnFilter(battle_zone_only=True)` now
  match membership in **any** lane's Battle Zone ("the Battle Zone" ⇒
  "a Battle Zone" per the double-lane rules).
- Effect scripts no longer read `state.active_zone_id` directly (Dodger was
  the only offender; its spawn-point helpers now use `battle_zone_ids()`).
  This convention is enforced by
  `tests/engine/test_lane_plumbing.py::test_effect_scripts_do_not_use_legacy_single_lane_accessors`.

### Setup

- `GameSetup.create_game()` initializes `battle_zones` and `wave_counters`
  per lane (mid zone of each lane, same wave count per lane) and spawns
  initial minions in every lane's Battle Zone with the correct binding.

### Client view (additive; single-lane clients unaffected)

`build_view()` now includes:

- `battle_zones`: `{lane_id: zone_id}`
- `wave_counters`: `{lane_id: int}`
- `active_zone_id` is kept as a legacy field: populated when the game has
  exactly one lane, `null` otherwise. Documented in
  `docs/CLIENT_INTEGRATION_GUIDE.md`.

### Multi-lane maps and loader (shipped after the prep)

- The loader (`engine/map_loader.py`) reads a top-level `"lanes"` key
  (`{"lane_1": [...], "lane_2": [...]}`, commit `fbfc67f`) and an optional
  `"battle_zones"` key (`{lane_id: zone label}`) for per-lane starting
  Battle Zones (`Board.starting_battle_zones`).
- A real two-lane map exists: `src/goa2/data/maps/across_the_river.json`
  (6 zones per lane, shared base zones, starting Battle Zones MidA2/MidB2).
  Maps are produced by the browser map editor (`tools/map_editor.html` —
  CSV geometry import, rotation, ★ starting-zone marker). The editor also
  loads the map image and solves the frontend's render calibration from two
  clicks; see `tools/map_editor.test.mjs` and
  `goa2-frontend/docs/superpowers/specs/2026-07-27-map-calibration-in-editor-design.md`.

### Double-lane endgame rules (shipped)

Spec: `docs/superpowers/specs/2026-07-05-double-lane-endgame-design.md`.

`CheckLanePushStep` is the endgame coordinator on multi-lane games. Pushes
triggered by the same check are simultaneous. Outcomes are pre-computed
before any mutation, then:

- Throne pushes favoring **both** teams ⇒ tie remedy.
- Throne push favoring **one** team ⇒ `LANE_PUSH` victory.
- Any wave counter at 0 after the flips ⇒ zone-count comparison at
  **post-push** positions (`map_logic.endgame_totals`): more total zones
  between your Throne and both Battle Zones ⇒ `LAST_PUSH` victory; equal ⇒
  tie remedy. Counters stay at 0, so **every subsequent push re-runs the
  comparison** until someone wins.
- Otherwise ⇒ mechanics-only `LanePushStep`s (pre-computed
  `target_zone_id`, `skip_wave_counter=True`).

Tie remedy: zones do not move, counters stay flipped, and each triggered
lane gets a full wipe + spawn-point respawn in its unmoved Battle Zone
(rulebook: "spawn all minions in the Zones they occupied before the push
and continue playing").

Single-lane games keep the classic rules (last flip ⇒ pusher wins),
entirely inside `LanePushStep`.

### Lane-bound ability respawns (shipped)

Necromancy/Necromastery (`scripts/dodger_effects.py:_build_respawn_steps`)
are hex-first: the player picks a spawn-point hex (only hexes whose lane
has limbo supply are offered), and the minion comes from **that lane's**
limbo supply (`RespawnMinionAtHexStep(lane_bound=True)`). Hexes outside any
lane (Tide of Darkness) fall back to the full supply.

### Tests

- `tests/engine/test_lane_plumbing.py` (20 tests): legacy back-compat
  (constructor kwargs, property setters, old-save JSON migration, multi-lane
  raising), lane helpers, minion lane binding (respawn / return-to-zone /
  heavy immunity), per-lane push on a synthetic two-lane board, multi-zone
  `BattleZoneFilter`, and the effect-script convention check.
- `tests/engine/test_double_lane_endgame.py` (16 tests): zone-count
  helpers, coordinator scenarios (throne precedence, post-push comparison,
  tie remedies, re-comparison, single-lane gate), Across the River
  integration.
- `tests/engine/test_lane_respawn_binding.py` (5 tests): lane-bound
  hex-first respawns.

## Still TBD

1. ~~**8–10 player setup config.**~~ DONE: `GameSetup.get_game_config()`
   takes `lane_count` (derived from the map in `create_game`). Two-lane
   games get 2×7 waves and 6 LC (6–8p) / 7 LC (9–10p) regardless of
   QUICK/LONG; extra heroes (>3 per team) are placed in empty spaces
   adjacent to their team's occupied hero spawn points, and setup raises
   if no placement exists. See `tests/engine/test_game_setup.py`
   (`TestTwoLaneConfig`, `TestTwoLaneGameSetup`).

2. **Simultaneous minion battles.** Pushes triggered by the same check ARE
   resolved simultaneously by the coordinator, but `MinionBattleStep` still
   queues battle *removals* in lane order (`battle_zones` dict order). For
   plain minion removal the ordering is not observable, so this is fine
   as-is; revisit if an effect ever makes it observable.

3. **Hero respawn / zone semantics on the second lane.** Anything that
   references zones by name or assumes one "Mid" (e.g. `playtest.py` dev
   tooling, some map-specific effect interpretations) should be audited
   against `across_the_river.json`. `playtest.py` still uses the legacy
   properties (fine — it is single-lane dev tooling; it will raise loudly
   if pointed at a two-lane game).

4. **Client support.** The view already carries `battle_zones` /
   `wave_counters`, but the frontend needs to render two lanes and the
   per-lane wave counters; `active_zone_id` will be `null` on double-lane
   games. Push/tie-undo `GameEvent`s are also still TODO (the push
   machinery is silent except `GAME_OVER`).

## Conventions going forward

- **Engine/effect code must not use** `state.active_zone_id`,
  `state.wave_counter`, or `board.lane` — use `battle_zones`,
  `wave_counters`, `board.lanes`, or the helpers
  (`battle_zone_ids()`, `battle_zone_for_lane()`, `lane_of_zone()`).
  The legacy properties exist only for old saves, dev tools, and
  single-lane tests, and raise on multi-lane games.
- "In the battle zone" checks in card effects should use `BattleZoneFilter`
  or `state.battle_zone_ids()` (never a single zone id) — card text reading
  "the Battle Zone" means "a Battle Zone" on multi-lane maps.
- Anything that spawns a minion must decide its `lane_id` (default is
  `"lane_1"`, which is always correct on single-lane maps).
