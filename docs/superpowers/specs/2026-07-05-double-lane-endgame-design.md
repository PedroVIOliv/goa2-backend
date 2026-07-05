# Double-Lane Endgame Design

**Date:** 2026-07-05
**Status:** Approved
**Scope:** Items 1 (remainder) and 2 of the TBD list in `docs/DOUBLE_LANE_PREP.md`,
plus lane-bound ability respawns (Necromancy/Necromastery).

## Background

The lane-aware plumbing (commit `85f7150`) and multi-lane map loading
(`fbfc67f`) are done, and a real two-lane map exists
(`src/goa2/data/maps/accross_the_river.json`, lanes of 6 zones each sharing
both base zones). What is missing is the double-lane *endgame*: the
last-wave zone-count comparison, simultaneous-push handling, and the tie
remedy. `LanePushStep` still implements only the single-lane rule (see the
`NOTE (double-lane TBD)` marker in `engine/steps/combat.py`).

### Rulebook text (double-lane endgame)

> Minions are bound to the Battle Zone they were originally spawned in for
> the purpose of respawning and when applying the "Minions Outside of the
> Battle Zone" rules. Minion Battles in each of the two Battle Zones are
> resolved separately, but happen simultaneously.
>
> After the last Wave counter on either Lane is flipped, each team counts
> how many Zones on each Lane are between their Throne and that lane's
> Battle Zone. The team with more total Zones between their Throne and both
> Battle Zones wins the game.
>
> If both teams would win at the same time as the result of the push, spawn
> all minions in the Zones they occupied before the push and continue
> playing until only one team wins the game.

## Locked rulings

1. **Comparison timing:** the zone count uses the pushed lane's Battle Zone
   at its **post-push** position ("as the result of the push").
2. **The rulebook's tie clause** covers **simultaneous throne pushes**: both
   lanes pushing onto the enemy bases at once (e.g. from the same
   end-of-round minion battles). Remedy: neither zone moves — the Battle
   Zones stay in the zones just before the respective bases — and a full
   minion respawn happens in both.
3. **Equal zone totals** in the last-wave comparison get the same remedy:
   the triggering push's zone move is cancelled, full respawn in that
   lane's (unmoved) Battle Zone, play continues. (Equal totals are
   reachable: on Across the River red_total + blue_total is always 6.)
4. **After a tie-undo**, the flipped Wave counter stays at 0 — the "last
   counter flipped" condition is permanently true, so **every subsequent
   push on any lane re-runs the comparison** (after applying that push).
   Throne-push wins remain instant throughout.
5. **Simultaneity window:** pushes triggered by the same
   `CheckLanePushStep` invocation are simultaneous. All push call sites
   (end-of-turn, end-of-round, Min/Tigerclaw effects) already funnel
   through `CheckLanePushStep`, and `LanePushStep` is never spawned
   directly by anything else.
6. **Single-lane games are untouched.** The single-lane last-flip rule
   (pusher wins immediately) differs materially from the comparison rule —
   e.g. a final push by Red deep inside Red territory wins under the
   single-lane rule but would lose the comparison. The multi-lane path is
   gated on `len(board.lanes) > 1`.
7. **Ability respawns respect lane binding** (rulebook: minions are bound
   to their original Battle Zone "for the purpose of respawning"). This
   fixes a real gap in Dodger's Necromancy/Necromastery, which today can
   respawn a lane-2-bound minion into lane 1's Battle Zone.

## Design

### Zone counting

Lanes are ordered `RedBase → BlueBase` (existing convention in
`map_logic.get_push_target_zone_id`). For a Battle Zone at index `i` in a
lane of length `n`:

- Red's distance = `i − 1` (zones strictly between Red base and the BZ)
- Blue's distance = `n − 2 − i`

A team's total is the sum over both lanes. New pure helpers in
`engine/map_logic.py`:

- `zones_between(state, team, lane_id, zone_id) -> int`
- `endgame_totals(state, bz_overrides: dict[str, str]) -> dict[TeamColor, int]`
  — totals computed with hypothetical post-push positions supplied as
  `{lane_id: zone_id}` overrides.

### Coordinator flow (`CheckLanePushStep.resolve`, multi-lane only)

1. Find triggered lanes via `check_lane_push_trigger` (unchanged). None →
   done.
2. **Pre-compute** each push's outcome — losing team, target zone,
   throne-reach — via `get_push_target_zone_id`. No mutation yet; the tie
   remedy never has to roll anything back because zone moves are only
   applied once the outcome is known.
3. **Flip counters** for all triggered lanes:
   `wave_counters[lane] = max(0, counter − 1)`.
4. **Throne check** (precedence over the count comparison):
   - Throne-reaching pushes favoring **both** teams → tie remedy, done.
   - Exactly **one** team → `TriggerGameOverStep(winner, "LANE_PUSH")`.
   - (Both throne pushes favoring the *same* team is just a win for that
     team — covered by the previous bullet since the winner set has one
     element.)
5. **Last-wave comparison:** if any lane's counter is now ≤ 0 (including
   from a previous tie), compute `endgame_totals` with the triggered
   lanes' post-push positions. Strictly more → `TriggerGameOverStep(winner,
   "LAST_PUSH")`. Equal → tie remedy.
6. **No endgame** → spawn a `LanePushStep` per triggered lane with the
   pre-computed target (`target_zone_id=...`, `skip_wave_counter=True`).

State is safe between sequential `LanePushStep` resolutions: a push only
moves its own lane's zone and minions, so pre-computed targets for sibling
lanes stay valid (and are pinned via `target_zone_id` regardless).

### Tie remedy

For each **triggered** lane:

- The Battle Zone does not move.
- Wipe minions physically inside that lane's BZ (same scoping as a normal
  push wipe; cross-lane strays inside the zone are wiped too, matching
  "Remove all Minions from old Battle Zone" being physical).
- Full spawn-point respawn in the same zone for both teams, candidates
  filtered by `m.lane_id` (this is what breaks the retrigger loop — the
  team that had 0 minions gets its supply back).
- Blocked spawn points queue displacements via `ResolveDisplacementStep`,
  as in a normal push.

Counters stay flipped. Untriggered lanes are untouched. Play continues;
throne wins and re-comparisons remain live.

### `LanePushStep` changes

Two new fields, both with back-compat defaults so persisted stacks and
single-lane games round-trip unchanged:

- `target_zone_id: str | None = None` — when set, skip the internal
  target/game-over computation and use this zone.
- `skip_wave_counter: bool = False` — when true, the coordinator already
  flipped the counter and handled endgame checks; the step only executes
  mechanics (move zone, wipe, respawn, displacements).

The wipe/respawn block is extracted into module helpers
(`_wipe_minions_in_zone`, `_respawn_minions_at_spawn_points` → returns
pending displacements) shared with the tie remedy. The
`NOTE (double-lane TBD)` comment is replaced with a pointer to the
coordinator.

### Lane-bound ability respawns (Necromancy/Necromastery)

`_build_respawn_steps` in `scripts/dodger_effects.py` flips to
**hex-first** selection:

1. `SelectStep` for the spawn-point hex — existing filters (friendly spawn
   point, `BattleZoneFilter`, not obstacle, in radius) **plus** a new
   constraint: the hex's lane must have ≥ 1 friendly limbo minion bound to
   it, so no dead-end choices are offered.
2. The minion choice is drawn from limbo minions bound to the **chosen
   hex's lane** (`lane_of_zone` of the hex's zone), one per type,
   auto-selected when unique.
3. `RespawnMinionAtHexStep` is extended to take the hex from context and
   resolve the lane-filtered minion selection internally (exact step shape
   decided in the implementation plan).

Single-lane games keep identical legality — only the selection *order*
changes (hex before minion). Dodger's existing tests are updated for the
new order.

### Verified interactions (no changes needed)

- **"Minions Outside of the Battle Zone"** (`ReturnMinionToZoneStep`) is
  already fully lane-correct: detection checks each minion against **its
  own lane's** BZ (a lane-2 minion inside lane 1's BZ counts as a stray),
  and the destination is its own lane's zone by shortest empty path.
- **Tie remedy vs strays:** strays outside the wiped BZ survive, exactly
  as in a normal push, and are pulled home by the return rule at its usual
  hook.
- **Transient cross-lane counting:** `check_lane_push_trigger` /
  `MinionBattleStep` count minions physically present in a zone regardless
  of binding. Strays are cleared after every action, so this is only
  transiently observable and matches physical-presence rules.
- **`RespawnMinionStep`** and push respawns already filter candidates by
  `m.lane_id`.

### Events, persistence, client contract

- **No new StepTypes.** Whether the hex-lane-supply constraint needs a new
  filter class is decided at plan time; if so, it gets a unique
  `FilterType` per CLAUDE.md.
- **Events:** parity with the existing push machinery, which is silent
  except for `GAME_OVER`. A push/tie-undo event type is deferred to the
  frontend double-lane work (`DOUBLE_LANE_PREP.md` TBD #6).
- **Persistence:** new step fields have defaults → serialization
  round-trips; `AnyStep` is auto-derived, nothing to hand-edit.
- **Client contract:** unchanged. `GameViewResponse` already carries
  `battle_zones`/`wave_counters`.

## Edge cases

| Case | Outcome |
|---|---|
| Throne push + last counter flip in same event | Throne precedence (step 4 before 5) |
| Both lanes flip last counters simultaneously | One comparison after both hypothetical moves |
| Push on lane B after lane A's counters hit 0 | Comparison still runs (any lane, any counter ≤ 0) |
| Double-throne tie where a counter also hit 0 | Tie remedy runs once (step 4 short-circuits) |
| Same team wins both throne pushes | Normal win, not a tie |
| Equal totals on single-lane game | N/A — single-lane keeps pusher-wins rule |

## Testing

New file `tests/engine/test_double_lane_endgame.py`, using the synthetic
two-lane board pattern from `test_lane_plumbing.py` plus Across the River
for at least one integration case:

1. `zones_between` / `endgame_totals` unit tests
2. Normal multi-lane push (counters > 0) → both lanes push, no game over
3. Last flip, unequal totals → `LAST_PUSH` winner; include a case where
   pre-push counting would name the *other* winner (proves post-push
   timing)
4. Last flip, equal totals → tie: zones unmoved, full respawn both teams,
   counter 0, game continues
5. Push after a tie → comparison re-runs and can end the game
6. Double throne push → tie remedy in both lanes
7. Single throne push → `LANE_PUSH` win unchanged
8. Necromancy/Necromastery on two lanes: each spawn point offers only its
   own lane's supply; lanes with empty supply excluded from hex options;
   respawned minion keeps its correct `lane_id`
9. Single-lane regression: full existing suite stays green
