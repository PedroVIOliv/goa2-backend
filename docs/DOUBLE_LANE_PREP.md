# Double-Lane Map Preparation

Status of the groundwork for supporting the 8–10 player double-lane map.
The engine is still **single-lane only** in practice (no double-lane map file
exists), but the data model and push machinery are now lane-aware, so adding
the second lane is an additive feature rather than a refactor.

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

### Tests

`tests/engine/test_lane_plumbing.py` (20 tests): legacy back-compat
(constructor kwargs, property setters, old-save JSON migration, multi-lane
raising), lane helpers, minion lane binding (respawn / return-to-zone /
heavy immunity), per-lane push on a synthetic two-lane board, multi-zone
`BattleZoneFilter`, and the effect-script convention check.

## Still TBD (the actual double-lane feature)

These were deliberately deferred — they are the feature itself and cannot be
meaningfully tested without a real two-lane map file.

1. **Double-lane map JSON + loader support.** No two-lane map exists. The
   loader (`engine/map_loader.py`) still only reads the single `"lane"` key
   (fed through the legacy migration); it needs a `"lanes"` map format
   (e.g. `{"lane_1": [...], "lane_2": [...]}`) and a real double-lane map
   with two sets of minion spawn points.

2. **Double-lane endgame rules.** `LanePushStep` implements the single-lane
   last-wave rule (last counter flipped ⇒ winner of that push wins). The
   double-lane rule is different: when the last Wave counter on either lane
   flips, compare **total zones between each team's Throne and both Battle
   Zones**; the team with more distance wins. A simultaneous-win tie means
   respawn minions in their pre-push zones and continue playing. There is a
   `NOTE (double-lane TBD)` marker at the wave-counter branch in
   `engine/steps/combat.py`.

3. **8–10 player setup config.** `GameSetup.get_game_config()` supports up
   to 6 players. Double-lane is 6–8 players (2×7 waves, 6 life) and 9–10
   players (2×7 waves, 7 life). Also missing: the rule that extra heroes
   (>3 per team) are placed in empty spaces **adjacent to** their team's
   occupied hero spawn points.

4. **Simultaneous minion battles.** `MinionBattleStep` resolves lanes
   sequentially (lane order = `battle_zones` dict order). The rules say
   "separately, but simultaneously" — if an effect ever makes ordering
   observable (e.g. a removal in lane 1 changing lane 2's count), the
   ordering/tie-breaker interaction needs a decision. For plain minion
   removal it is not observable, so this is likely fine as-is.

5. **Hero respawn / zone semantics on the second lane.** Anything that
   references zones by name or assumes one "Mid" (e.g. `playtest.py` dev
   tooling, some map-specific effect interpretations) should be audited when
   the real map exists. `playtest.py` still uses the legacy properties
   (fine — it is single-lane dev tooling; it will raise loudly if pointed at
   a two-lane game).

6. **Client support.** The view already carries `battle_zones` /
   `wave_counters`, but the frontend needs to render two lanes and the
   per-lane wave counters; `active_zone_id` will be `null` on double-lane
   games.

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
