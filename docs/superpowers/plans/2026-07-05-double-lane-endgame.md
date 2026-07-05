# Double-Lane Endgame Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the double-lane endgame rules (last-wave zone-count comparison, simultaneous-push handling, tie remedy) and lane-bound ability respawns, per `docs/superpowers/specs/2026-07-05-double-lane-endgame-design.md`.

**Architecture:** `CheckLanePushStep` becomes the multi-lane coordinator: it pre-computes every triggered push's outcome *before mutating*, decides throne wins / last-wave comparison / tie remedy, and only then spawns mechanical `LanePushStep`s with pre-computed targets. Single-lane games keep the existing rules untouched (gated on `len(board.lanes) > 1`). Dodger's Necromancy/Necromastery flips to hex-first selection so the respawned minion always comes from the chosen hex's lane supply.

**Tech Stack:** Python 3.11+, Pydantic V2, pytest.

## Global Constraints

- Run tests with `PYTHONPATH=src uv run pytest <path> -q` from the repo root.
- Commit directly on `main`. No `Co-Authored-By` lines, no tool mentions in commit messages.
- **No new `StepType`s and no new `FilterType`s** in this plan. New fields on existing steps must have defaults (serialization round-trip; old saves).
- Engine/effect code must NOT use `state.active_zone_id`, `state.wave_counter`, or `board.lane` (legacy accessors raise on multi-lane). Use `state.battle_zones`, `state.wave_counters`, `board.lanes`, `state.battle_zone_for_lane()`, `state.lane_of_zone()`.
- Effect code must not read `entity_locations`/`unit_locations` directly for heroes — use `state.has_board_presence()`, `state.get_position()` etc. (multipiece conventions).
- Test files must have unique basenames across `tests/` (no `__init__.py` in test dirs) — helpers cannot be imported between test files; duplicate small fixtures instead.
- Before the final task, the full suite must pass: `PYTHONPATH=src uv run pytest tests/ -q`.

## File Structure

- Modify `src/goa2/engine/map_logic.py` — add `zones_between()` and `endgame_totals()` (pure helpers).
- Modify `src/goa2/engine/steps/combat.py` — extract `_wipe_minions_in_zone()` / `_respawn_minions_at_spawn_points()`; add `target_zone_id`/`skip_wave_counter` to `LanePushStep`; multi-lane coordinator in `CheckLanePushStep`; lane-bound mode on `RespawnMinionAtHexStep`.
- Modify `src/goa2/scripts/dodger_effects.py` — `_build_respawn_steps()` becomes a single lane-bound `RespawnMinionAtHexStep`.
- Create `tests/engine/test_double_lane_endgame.py` — helpers + coordinator scenarios + Across the River integration.
- Create `tests/engine/test_lane_respawn_binding.py` — Necromancy/Necromastery lane binding.
- Modify `docs/DOUBLE_LANE_PREP.md` — refresh stale status.

---

### Task 1: Zone-count helpers in `map_logic.py`

**Files:**
- Modify: `src/goa2/engine/map_logic.py` (append after `get_push_target_zone_id`, ~line 80)
- Test: `tests/engine/test_double_lane_endgame.py` (new file)

**Interfaces:**
- Consumes: `state.board.lanes: dict[str, list[str]]`, `state.battle_zones: dict[str, str]` (existing).
- Produces: `zones_between(state: GameState, team: TeamColor, lane_id: str, zone_id: str) -> int` and `endgame_totals(state: GameState, bz_overrides: dict[str, str] | None = None) -> dict[TeamColor, int]` in `goa2.engine.map_logic`. Task 3 calls both.

- [x] **Step 1: Write the failing tests**

Create `tests/engine/test_double_lane_endgame.py`:

```python
"""Double-lane endgame: zone-count helpers and CheckLanePushStep coordinator.

Spec: docs/superpowers/specs/2026-07-05-double-lane-endgame-design.md
Lanes are ordered RedBase -> BlueBase. For a Battle Zone at index i in a
lane of length n: red distance = i - 1, blue distance = n - 2 - i
(zones strictly between the throne and the BZ).
"""

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Minion, MinionType, Team, TeamColor
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.domain.types import UnitID
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.map_logic import endgame_totals, zones_between
from goa2.engine.steps import CheckLanePushStep


def _row_hexes(q_start: int, q_end: int, r: int) -> list[Hex]:
    return [Hex(q=q, r=r, s=-q - r) for q in range(q_start, q_end + 1)]


def _make_endgame_state(waves: int = 5) -> GameState:
    """Two disconnected 5-zone lanes (rows r=0 and r=4).

    Zone layout per lane: rbase | rbeach | mid | bbeach | bbase.
    Bases have no hexes; the three middle zones have 4 hexes each with a
    RED melee spawn point on the leftmost hex and a BLUE one on the
    rightmost. Battle zones start at each lane's mid.
    """
    board = Board()
    lanes: dict[str, list[str]] = {}
    for lane_key, r in (("l1", 0), ("l2", 4)):
        zone_ids = [f"{lane_key}_{n}" for n in ("rbase", "rbeach", "mid", "bbeach", "bbase")]
        lanes[f"lane_{lane_key[-1]}"] = zone_ids
        board.zones[zone_ids[0]] = Zone(id=zone_ids[0], hexes=set())
        board.zones[zone_ids[4]] = Zone(id=zone_ids[4], hexes=set())
        q = 0
        for zone_id in zone_ids[1:4]:
            hexes = _row_hexes(q, q + 3, r)
            board.zones[zone_id] = Zone(
                id=zone_id,
                hexes=set(hexes),
                spawn_points=[
                    SpawnPoint(
                        location=hexes[0],
                        team=TeamColor.RED,
                        type=SpawnType.MINION,
                        minion_type=MinionType.MELEE,
                    ),
                    SpawnPoint(
                        location=hexes[3],
                        team=TeamColor.BLUE,
                        type=SpawnType.MINION,
                        minion_type=MinionType.MELEE,
                    ),
                ],
            )
            for h in hexes:
                board.tiles[h] = Tile(hex=h, zone_id=zone_id)
            q += 4
    board.lanes = lanes
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )
    state.battle_zones = {"lane_1": "l1_mid", "lane_2": "l2_mid"}
    state.wave_counters = {"lane_1": waves, "lane_2": waves}
    return state


def _add_minion(state, minion_id, team, lane_id, at=None):
    m = Minion(
        id=UnitID(minion_id), name=minion_id, team=team,
        type=MinionType.MELEE, lane_id=lane_id,
    )
    state.teams[team].minions.append(m)
    if at is not None:
        state.place_entity(minion_id, at)
    return m


class TestZoneCounting:
    def test_zones_between_mid(self):
        state = _make_endgame_state()
        # 5-zone lane, mid is index 2: one zone between each throne and the BZ
        assert zones_between(state, TeamColor.RED, "lane_1", "l1_mid") == 1
        assert zones_between(state, TeamColor.BLUE, "lane_1", "l1_mid") == 1

    def test_zones_between_asymmetric(self):
        state = _make_endgame_state()
        # bbeach is index 3: red has rbeach+mid between, blue has none
        assert zones_between(state, TeamColor.RED, "lane_1", "l1_bbeach") == 2
        assert zones_between(state, TeamColor.BLUE, "lane_1", "l1_bbeach") == 0
        # rbeach is index 1
        assert zones_between(state, TeamColor.RED, "lane_1", "l1_rbeach") == 0
        assert zones_between(state, TeamColor.BLUE, "lane_1", "l1_rbeach") == 2

    def test_zones_between_unknown_zone_is_zero(self):
        state = _make_endgame_state()
        assert zones_between(state, TeamColor.RED, "lane_1", "nope") == 0

    def test_endgame_totals_current_positions(self):
        state = _make_endgame_state()
        totals = endgame_totals(state)
        assert totals == {TeamColor.RED: 2, TeamColor.BLUE: 2}

    def test_endgame_totals_with_overrides(self):
        state = _make_endgame_state()
        totals = endgame_totals(state, {"lane_1": "l1_bbeach"})
        # lane_1 at bbeach (red 2, blue 0) + lane_2 at mid (red 1, blue 1)
        assert totals == {TeamColor.RED: 3, TeamColor.BLUE: 1}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_double_lane_endgame.py -q`
Expected: FAIL — `ImportError: cannot import name 'endgame_totals' from 'goa2.engine.map_logic'`

- [x] **Step 3: Implement the helpers**

Append to `src/goa2/engine/map_logic.py` (after `get_push_target_zone_id`, before `count_enemies`):

```python
def zones_between(state: GameState, team: TeamColor, lane_id: str, zone_id: str) -> int:
    """
    Number of zones strictly between a team's Throne and the given zone on
    a lane. Lanes are ordered RedBase -> BlueBase; for a zone at index i in
    a lane of length n: RED distance = i - 1, BLUE distance = n - 2 - i.
    Returns 0 for zones not on the lane.
    """
    lane = state.board.lanes.get(lane_id, [])
    if zone_id not in lane:
        return 0
    idx = lane.index(zone_id)
    if team == TeamColor.RED:
        return max(0, idx - 1)
    return max(0, len(lane) - 2 - idx)


def endgame_totals(
    state: GameState, bz_overrides: dict[str, str] | None = None
) -> dict[TeamColor, int]:
    """
    Total zones between each team's Throne and every lane's Battle Zone
    (the double-lane last-wave comparison). `bz_overrides` supplies
    hypothetical post-push positions as {lane_id: zone_id}.
    """
    overrides = bz_overrides or {}
    totals = {TeamColor.RED: 0, TeamColor.BLUE: 0}
    for lane_id, current_zone_id in state.battle_zones.items():
        zone_id = overrides.get(lane_id, current_zone_id)
        for team in (TeamColor.RED, TeamColor.BLUE):
            totals[team] += zones_between(state, team, lane_id, zone_id)
    return totals
```

- [x] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_double_lane_endgame.py -q`
Expected: 5 passed

- [x] **Step 5: Commit**

```bash
git add src/goa2/engine/map_logic.py tests/engine/test_double_lane_endgame.py
git commit -m "feat: zone-count helpers for double-lane endgame"
```

---

### Task 2: Extract push mechanics; pre-computed `LanePushStep` fields

**Files:**
- Modify: `src/goa2/engine/steps/combat.py` (LanePushStep, ~lines 1098–1244)
- Test: `tests/engine/test_double_lane_endgame.py` (append), existing `tests/engine/test_lane_push.py` as regression

**Interfaces:**
- Consumes: `zones_between`/`endgame_totals` — not yet; this task is mechanics only.
- Produces (module-level in `engine/steps/combat.py`, used by Task 3):
  - `_wipe_minions_in_zone(state: GameState, zone_id: str) -> None`
  - `_respawn_minions_at_spawn_points(state: GameState, lane_id: str, zone_id: str) -> list[tuple[str, Hex]]` (pending displacements)
  - `LanePushStep(lane_id, losing_team, target_zone_id: str | None = None, skip_wave_counter: bool = False)` — when both new fields are set, the step performs mechanics only (no counter flip, no game-over checks).

- [x] **Step 1: Write the failing tests**

Append to `tests/engine/test_double_lane_endgame.py`:

```python
from goa2.engine.steps import LanePushStep


class TestLanePushMechanicsOnly:
    def test_precomputed_push_skips_counter_and_endgame(self):
        state = _make_endgame_state(waves=1)
        _add_minion(state, "blue_1", TeamColor.BLUE, "lane_1",
                    at=_row_hexes(4, 7, 0)[3])  # in l1_mid
        _add_minion(state, "red_limbo", TeamColor.RED, "lane_1")  # limbo

        push_steps(state, [LanePushStep(
            lane_id="lane_1", losing_team=TeamColor.RED,
            target_zone_id="l1_rbeach", skip_wave_counter=True,
        )])
        result = process_stack(state)

        assert result.input_request is None
        # counter untouched, no game over despite waves=1
        assert state.wave_counters["lane_1"] == 1
        assert state.winner is None
        # zone moved to the pre-computed target
        assert state.battle_zones["lane_1"] == "l1_rbeach"
        # old-zone minion wiped, respawns happened in the new zone
        blue_loc = state.unit_locations.get("blue_1")
        rbeach_hexes = state.board.zones["l1_rbeach"].hexes
        assert blue_loc in rbeach_hexes
        assert state.unit_locations.get("red_limbo") in rbeach_hexes

    def test_new_fields_round_trip_serialization(self):
        state = _make_endgame_state()
        push_steps(state, [LanePushStep(
            lane_id="lane_2", losing_team=TeamColor.BLUE,
            target_zone_id="l2_bbeach", skip_wave_counter=True,
        )])
        data = state.model_dump(mode="json")
        restored = GameState.model_validate(data)
        s = restored.execution_stack[0]
        assert type(s).__name__ == "LanePushStep"
        assert s.target_zone_id == "l2_bbeach"
        assert s.skip_wave_counter is True
```

- [x] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_double_lane_endgame.py -q`
Expected: FAIL — `target_zone_id` unexpected keyword / validation error

- [x] **Step 3: Extract helpers and refactor `LanePushStep`**

In `src/goa2/engine/steps/combat.py`, add module-level helpers directly above `class CheckLanePushStep` (the code is moved out of `LanePushStep.resolve`, unchanged in behavior):

```python
def _wipe_minions_in_zone(state: GameState, zone_id: str) -> None:
    """Remove every minion physically inside the zone (push wipe)."""
    zone = state.board.zones.get(zone_id)
    if not zone:
        return
    to_remove = []
    for uid, loc in state.unit_locations.items():
        if loc in zone.hexes:
            unit = state.get_unit(UnitID(uid))
            if hasattr(unit, "type") and hasattr(unit, "value"):  # Duck typing Minion
                to_remove.append(uid)
    for uid in to_remove:
        state.remove_unit(uid)
        logger.debug(f"   [PUSH] Wiped {uid} from zone {zone_id}.")


def _respawn_minions_at_spawn_points(
    state: GameState, lane_id: str, zone_id: str
) -> list[tuple[str, Hex]]:
    """
    Spawn limbo minions bound to `lane_id` at the zone's minion spawn
    points (both teams). Returns blocked spawns as pending displacements.
    """
    from goa2.engine.steps.markers import _remove_token_from_board

    zone = state.board.zones.get(zone_id)
    pending_displacements: list[tuple[str, Hex]] = []
    if not zone:
        return pending_displacements

    for sp in zone.spawn_points:
        if not sp.is_minion_spawn:
            continue
        team = state.teams.get(sp.team)
        if not team:
            continue
        candidate = next(
            (
                m
                for m in team.minions
                if m.type == sp.minion_type
                and m.lane_id == lane_id
                and m.id not in state.unit_locations
            ),
            None,
        )
        if not candidate:
            continue
        tile = state.board.get_tile(sp.location)
        if tile and not tile.is_occupied:
            state.move_unit(candidate.id, sp.location)
            logger.debug(f"   [PUSH] Spawning {candidate.id} at {sp.location}")
        else:
            occupant_id = str(tile.occupant_id) if tile and tile.occupant_id else None
            occupant = (
                state.misc_entities.get(BoardEntityID(occupant_id)) if occupant_id else None
            )
            if isinstance(occupant, Token) and occupant_id:
                _remove_token_from_board(state, occupant_id)
                state.move_unit(candidate.id, sp.location)
                logger.debug(
                    f"   [PUSH] Removed token {occupant_id} and spawned "
                    f"{candidate.id} at {sp.location}"
                )
            else:
                logger.debug(f"   [PUSH] Spawn blocked at {sp.location} (Displacement Queued)")
                pending_displacements.append((str(candidate.id), sp.location))
    return pending_displacements
```

Then rewrite `LanePushStep` fields and `resolve` (keeping the docstring, replacing the body — the wipe/respawn sections are DELETED from resolve and replaced with helper calls):

```python
class LanePushStep(GameStep):
    """
    Executes a Lane Push:
    1. Removes Wave Counter (unless skip_wave_counter).
    2. Moves Battle Zone.
    3. Wipes Minions in old zone.
    4. Respawns Minions in new zone.
    5. Checks Victory Conditions (Throne or Last Push) — single-lane only;
       on multi-lane games CheckLanePushStep decides the endgame BEFORE
       spawning this step and passes target_zone_id/skip_wave_counter.
    """

    type: StepType = StepType.LANE_PUSH
    lane_id: str = DEFAULT_LANE_ID
    losing_team: TeamColor
    # Set by CheckLanePushStep on multi-lane games (mechanics-only mode).
    target_zone_id: str | None = None
    skip_wave_counter: bool = False

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.map_logic import get_push_target_zone_id
        from goa2.engine.steps.movement import ResolveDisplacementStep

        logger.debug(
            f"   [PUSH] Lane Push Triggered on {self.lane_id}! "
            f"Losing Team: {self.losing_team.name}"
        )

        if not self.skip_wave_counter:
            remaining_waves = state.wave_counters.get(self.lane_id, 0) - 1
            state.wave_counters[self.lane_id] = remaining_waves
            logger.debug(
                f"   [PUSH] Wave Counter removed ({self.lane_id}). Remaining: {remaining_waves}"
            )
            if remaining_waves <= 0:
                # Single-lane last-push rule (pusher wins). Multi-lane games
                # never reach this branch: the coordinator resolves the
                # comparison and spawns this step with skip_wave_counter=True.
                logger.debug("   [GAME OVER] Last Push Victory!")
                winning_team = (
                    TeamColor.BLUE if self.losing_team == TeamColor.RED else TeamColor.RED
                )
                return StepResult(
                    is_finished=True,
                    new_steps=[TriggerGameOverStep(winner=winning_team, condition="LAST_PUSH")],
                )

        if self.target_zone_id is not None:
            next_zone_id: str | None = self.target_zone_id
        else:
            next_zone_id, is_game_over = get_push_target_zone_id(
                state, self.losing_team, self.lane_id
            )
            if is_game_over:
                logger.debug(
                    f"   [GAME OVER] Lane Push Victory! {self.losing_team.name} Throne reached."
                )
                winning_team = (
                    TeamColor.BLUE if self.losing_team == TeamColor.RED else TeamColor.RED
                )
                return StepResult(
                    is_finished=True,
                    new_steps=[TriggerGameOverStep(winner=winning_team, condition="LANE_PUSH")],
                )

        if not next_zone_id:
            logger.debug("   [ERROR] Could not determine next zone for push.")
            return StepResult(is_finished=True)

        current_zone_id = state.battle_zone_for_lane(self.lane_id)
        if not current_zone_id:
            logger.debug("   [ERROR] No active zone for push.")
            return StepResult(is_finished=True)

        _wipe_minions_in_zone(state, current_zone_id)

        logger.debug(f"   [PUSH] Battle Zone moved: {current_zone_id} -> {next_zone_id}")
        state.battle_zones[self.lane_id] = next_zone_id

        pending_displacements = _respawn_minions_at_spawn_points(
            state, self.lane_id, next_zone_id
        )

        if pending_displacements:
            return StepResult(
                is_finished=True,
                new_steps=[ResolveDisplacementStep(displacements=pending_displacements)],
            )

        return StepResult(is_finished=True)
```

Keep existing imports (`Token`, `BoardEntityID`, `cast` may become unused — remove `cast` if nothing else uses it; `ruff` will tell you).

- [x] **Step 4: Run new tests and the lane regression suites**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_double_lane_endgame.py tests/engine/test_lane_push.py tests/engine/test_lane_plumbing.py -q`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add src/goa2/engine/steps/combat.py tests/engine/test_double_lane_endgame.py
git commit -m "refactor: extract push mechanics; mechanics-only mode for LanePushStep"
```

---

### Task 3: Multi-lane coordinator in `CheckLanePushStep`

**Files:**
- Modify: `src/goa2/engine/steps/combat.py` (`CheckLanePushStep`, ~lines 1064–1096)
- Test: `tests/engine/test_double_lane_endgame.py` (append)

**Interfaces:**
- Consumes: `zones_between`/`endgame_totals` (Task 1); `_wipe_minions_in_zone`/`_respawn_minions_at_spawn_points` and mechanics-only `LanePushStep` (Task 2); existing `check_lane_push_trigger`, `get_push_target_zone_id`, `TriggerGameOverStep(winner, condition)`.
- Produces: multi-lane endgame decisions. Victory conditions used: `"LANE_PUSH"` (throne) and `"LAST_PUSH"` (comparison) — same strings as today.

- [x] **Step 1: Write the failing tests**

Append to `tests/engine/test_double_lane_endgame.py`:

```python
def _mid_hexes(lane_key: str) -> list[Hex]:
    r = 0 if lane_key == "l1" else 4
    return _row_hexes(4, 7, r)


def _run_check(state) -> None:
    push_steps(state, [CheckLanePushStep()])
    result = process_stack(state)
    assert result.input_request is None


class TestCoordinator:
    def test_normal_multilane_push(self):
        state = _make_endgame_state(waves=5)
        # Red loses lane_1 (blue minion alone in l1_mid); blue loses lane_2
        _add_minion(state, "b1", TeamColor.BLUE, "lane_1", at=_mid_hexes("l1")[3])
        _add_minion(state, "r2", TeamColor.RED, "lane_2", at=_mid_hexes("l2")[0])
        _run_check(state)
        assert state.winner is None
        assert state.battle_zones == {"lane_1": "l1_rbeach", "lane_2": "l2_bbeach"}
        assert state.wave_counters == {"lane_1": 4, "lane_2": 4}

    def test_single_throne_push_wins(self):
        state = _make_endgame_state(waves=5)
        state.battle_zones["lane_1"] = "l1_rbeach"
        # Red loses at rbeach -> next index 0 = red base -> blue wins
        _add_minion(state, "b1", TeamColor.BLUE, "lane_1",
                    at=_row_hexes(0, 3, 0)[3])
        _run_check(state)
        assert state.winner == TeamColor.BLUE
        assert state.victory_condition == "LANE_PUSH"

    def test_double_throne_push_is_tie_remedy(self):
        state = _make_endgame_state(waves=5)
        state.battle_zones = {"lane_1": "l1_rbeach", "lane_2": "l2_bbeach"}
        # lane_1: red loses -> would hit red base (blue would win)
        _add_minion(state, "b1", TeamColor.BLUE, "lane_1", at=_row_hexes(0, 3, 0)[3])
        # lane_2: blue loses -> would hit blue base (red would win)
        _add_minion(state, "r2", TeamColor.RED, "lane_2", at=_row_hexes(8, 11, 4)[0])
        # limbo supply so the tie respawn has something to place
        _add_minion(state, "r1_limbo", TeamColor.RED, "lane_1")
        _add_minion(state, "b2_limbo", TeamColor.BLUE, "lane_2")
        _run_check(state)
        assert state.winner is None
        # zones did not move; counters still flipped
        assert state.battle_zones == {"lane_1": "l1_rbeach", "lane_2": "l2_bbeach"}
        assert state.wave_counters == {"lane_1": 4, "lane_2": 4}
        # full respawn: the wiped-out teams got their supply back in-place
        assert state.unit_locations.get("r1_limbo") in state.board.zones["l1_rbeach"].hexes
        assert state.unit_locations.get("b2_limbo") in state.board.zones["l2_bbeach"].hexes
        # survivors were wiped and respawned at spawn points of the same zone
        assert state.unit_locations.get("b1") in state.board.zones["l1_rbeach"].hexes

    def test_last_wave_comparison_uses_post_push_position(self):
        state = _make_endgame_state(waves=5)
        state.wave_counters = {"lane_1": 1, "lane_2": 5}
        # lane_1 at mid, red loses -> post-push l1_rbeach (red 0, blue 2)
        # lane_2 stays at mid (red 1, blue 1)
        # post-push totals: red 1, blue 3 -> BLUE wins.
        # (pre-push totals would be 2-2 — a tie — so this asserts timing.)
        _add_minion(state, "b1", TeamColor.BLUE, "lane_1", at=_mid_hexes("l1")[3])
        _run_check(state)
        assert state.winner == TeamColor.BLUE
        assert state.victory_condition == "LAST_PUSH"

    def test_last_wave_equal_totals_is_tie_remedy(self):
        state = _make_endgame_state(waves=5)
        state.wave_counters = {"lane_1": 1, "lane_2": 5}
        state.battle_zones = {"lane_1": "l1_rbeach", "lane_2": "l2_mid"}
        # lane_1: blue loses at rbeach -> post-push l1_mid (red 1, blue 1)
        # lane_2 at mid (red 1, blue 1) -> totals 2-2 -> tie remedy
        _add_minion(state, "r1", TeamColor.RED, "lane_1", at=_row_hexes(0, 3, 0)[0])
        _add_minion(state, "b1_limbo", TeamColor.BLUE, "lane_1")
        _run_check(state)
        assert state.winner is None
        assert state.battle_zones["lane_1"] == "l1_rbeach"  # unmoved
        assert state.wave_counters["lane_1"] == 0           # counter stays flipped
        # full respawn in the unmoved zone for both teams
        rbeach = state.board.zones["l1_rbeach"].hexes
        assert state.unit_locations.get("r1") in rbeach
        assert state.unit_locations.get("b1_limbo") in rbeach
        # untriggered lane untouched
        assert state.battle_zones["lane_2"] == "l2_mid"

    def test_push_after_tie_recompares_from_any_lane(self):
        state = _make_endgame_state(waves=5)
        # lane_1 exhausted earlier (tie happened); push now occurs on lane_2
        state.wave_counters = {"lane_1": 0, "lane_2": 3}
        # lane_2: blue loses at mid -> post-push l2_bbeach (red 2, blue 0)
        # lane_1 at mid (red 1, blue 1) -> totals red 3, blue 1 -> RED wins
        _add_minion(state, "r2", TeamColor.RED, "lane_2", at=_mid_hexes("l2")[0])
        _run_check(state)
        assert state.winner == TeamColor.RED
        assert state.victory_condition == "LAST_PUSH"

    def test_single_lane_game_keeps_pusher_wins_rule(self):
        state = _make_endgame_state(waves=1)
        # Reduce to a single-lane game
        state.board.lanes = {"lane_1": state.board.lanes["lane_1"]}
        state.battle_zones = {"lane_1": "l1_rbeach"}
        state.wave_counters = {"lane_1": 1}
        # Red pushes (blue loses) from rbeach: comparison would favor BLUE
        # (post-push mid: 1-1... pre-push rbeach: red 0 blue 2) but the
        # single-lane rule says the pusher (RED) wins on the last flip.
        _add_minion(state, "r1", TeamColor.RED, "lane_1", at=_row_hexes(0, 3, 0)[0])
        _run_check(state)
        assert state.winner == TeamColor.RED
        assert state.victory_condition == "LAST_PUSH"
```

- [x] **Step 2: Run tests to verify the new ones fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_double_lane_endgame.py -q`
Expected: `TestCoordinator` tests FAIL (e.g. double-throne currently ends the game for whichever lane resolves first); `test_normal_multilane_push` and `test_single_lane_game_keeps_pusher_wins_rule` may already pass — that is fine.

- [x] **Step 3: Implement the coordinator**

Replace `CheckLanePushStep` in `src/goa2/engine/steps/combat.py`:

```python
class CheckLanePushStep(GameStep):
    """
    Checks if a Battle Zone meets the condition for a Lane Push (0 minions
    for one team) and decides what happens.

    Single-lane games: spawns a classic LanePushStep (which owns the wave
    counter and endgame rules).

    Multi-lane games: acts as the endgame coordinator. Pushes triggered by
    the same check are simultaneous per the double-lane rules. Outcomes are
    pre-computed BEFORE any mutation, then:
      - throne pushes favoring both teams  -> tie remedy
      - throne push favoring one team      -> LANE_PUSH victory
      - any wave counter at 0 after flips  -> zone-count comparison at
        post-push positions (LAST_PUSH victory, or tie remedy on equal)
      - otherwise                          -> mechanics-only LanePushSteps

    Tie remedy: zones do not move, counters stay flipped, and each
    triggered lane gets a full wipe + spawn-point respawn in its unmoved
    Battle Zone (rulebook: "spawn all minions in the Zones they occupied
    before the push and continue playing").

    With lane_id=None (default) every lane is checked, so existing call
    sites remain correct on multi-lane maps.
    """

    type: StepType = StepType.CHECK_LANE_PUSH
    lane_id: str | None = None

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.map_logic import check_lane_push_trigger

        lanes_to_check = (
            [self.lane_id] if self.lane_id is not None else list(state.battle_zones.keys())
        )

        triggered: list[tuple[str, TeamColor]] = []
        for lane_id in lanes_to_check:
            zone_id = state.battle_zone_for_lane(lane_id)
            if not zone_id:
                continue
            losing_team = check_lane_push_trigger(state, zone_id)
            if losing_team:
                logger.debug(
                    f"   [CHECK] Lane Push Condition Met for {losing_team.name} on {lane_id}"
                )
                triggered.append((lane_id, losing_team))

        if not triggered:
            return StepResult(is_finished=True)

        if len(state.board.lanes) <= 1:
            return StepResult(
                is_finished=True,
                new_steps=[
                    LanePushStep(lane_id=lane_id, losing_team=losing_team)
                    for lane_id, losing_team in triggered
                ],
            )

        return self._resolve_multi_lane(state, triggered)

    def _resolve_multi_lane(
        self, state: GameState, triggered: list[tuple[str, TeamColor]]
    ) -> StepResult:
        from goa2.engine.map_logic import endgame_totals, get_push_target_zone_id

        # Pre-compute every push's outcome before mutating anything.
        outcomes: list[tuple[str, TeamColor, str | None, bool]] = []
        for lane_id, losing_team in triggered:
            target, reaches_throne = get_push_target_zone_id(state, losing_team, lane_id)
            outcomes.append((lane_id, losing_team, target, reaches_throne))

        # Flip counters for all triggered lanes (they stay flipped even on a tie).
        for lane_id, _, _, _ in outcomes:
            state.wave_counters[lane_id] = max(0, state.wave_counters.get(lane_id, 0) - 1)

        # Throne precedence.
        throne_winners = {
            TeamColor.BLUE if losing_team == TeamColor.RED else TeamColor.RED
            for _, losing_team, _, reaches_throne in outcomes
            if reaches_throne
        }
        if len(throne_winners) == 2:
            logger.debug("   [ENDGAME] Simultaneous throne pushes — tie remedy.")
            return self._tie_remedy(state, outcomes)
        if len(throne_winners) == 1:
            winner = throne_winners.pop()
            logger.debug(f"   [GAME OVER] Lane Push Victory for {winner.name}!")
            return StepResult(
                is_finished=True,
                new_steps=[TriggerGameOverStep(winner=winner, condition="LANE_PUSH")],
            )

        # Last-wave comparison: once any lane's counters are exhausted, every
        # push re-runs the comparison at post-push positions.
        if any(count <= 0 for count in state.wave_counters.values()):
            overrides = {
                lane_id: target for lane_id, _, target, _ in outcomes if target is not None
            }
            totals = endgame_totals(state, overrides)
            red, blue = totals[TeamColor.RED], totals[TeamColor.BLUE]
            logger.debug(f"   [ENDGAME] Last-wave comparison: RED {red} vs BLUE {blue}")
            if red != blue:
                winner = TeamColor.RED if red > blue else TeamColor.BLUE
                return StepResult(
                    is_finished=True,
                    new_steps=[TriggerGameOverStep(winner=winner, condition="LAST_PUSH")],
                )
            logger.debug("   [ENDGAME] Equal totals — tie remedy, play continues.")
            return self._tie_remedy(state, outcomes)

        # No endgame: mechanics-only pushes with pre-computed targets.
        push_new_steps: list[GameStep] = []
        for lane_id, losing_team, target, _ in outcomes:
            if target is None:
                logger.debug(f"   [ERROR] No push target for {lane_id}; skipping.")
                continue
            push_new_steps.append(
                LanePushStep(
                    lane_id=lane_id,
                    losing_team=losing_team,
                    target_zone_id=target,
                    skip_wave_counter=True,
                )
            )
        return StepResult(is_finished=True, new_steps=push_new_steps)

    def _tie_remedy(
        self, state: GameState, outcomes: list[tuple[str, TeamColor, str | None, bool]]
    ) -> StepResult:
        from goa2.engine.steps.movement import ResolveDisplacementStep

        displacements: list[tuple[str, Hex]] = []
        for lane_id, _, _, _ in outcomes:
            zone_id = state.battle_zone_for_lane(lane_id)
            if not zone_id:
                continue
            _wipe_minions_in_zone(state, zone_id)
            displacements.extend(_respawn_minions_at_spawn_points(state, lane_id, zone_id))
        if displacements:
            return StepResult(
                is_finished=True,
                new_steps=[ResolveDisplacementStep(displacements=displacements)],
            )
        return StepResult(is_finished=True)
```

- [x] **Step 4: Run the endgame tests and lane regressions**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_double_lane_endgame.py tests/engine/test_lane_push.py tests/engine/test_lane_plumbing.py -q`
Expected: all pass

- [x] **Step 5: Run the full engine suite (coordinator touches shared machinery)**

Run: `PYTHONPATH=src uv run pytest tests/engine/ -q`
Expected: all pass. If a test fails because it constructed `CheckLanePushStep`/`LanePushStep` scenarios directly, fix the test only if its *setup* relied on removed internals; behavior expectations must not change for single-lane games.

- [x] **Step 6: Commit**

```bash
git add src/goa2/engine/steps/combat.py tests/engine/test_double_lane_endgame.py
git commit -m "feat: double-lane endgame coordinator in CheckLanePushStep"
```

---

### Task 4: Across the River integration test

**Files:**
- Test: `tests/engine/test_double_lane_endgame.py` (append)

**Interfaces:**
- Consumes: `load_map` (`goa2.engine.map_loader`), Task 1 helpers, Task 3 coordinator.
- Produces: regression coverage on the real two-lane map.

- [x] **Step 1: Write the test (should pass immediately — it validates integration, not new code)**

Append to `tests/engine/test_double_lane_endgame.py`:

```python
class TestAcrossTheRiver:
    def _load_state(self) -> GameState:
        from goa2.engine.map_loader import load_map

        board = load_map("src/goa2/data/maps/accross_the_river.json")
        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
        )
        state.battle_zones = dict(board.starting_battle_zones)
        state.wave_counters = {lane_id: 7 for lane_id in board.lanes}
        return state

    def test_starting_position_is_symmetric(self):
        state = self._load_state()
        assert len(state.board.lanes) == 2
        assert all(len(lane) == 6 for lane in state.board.lanes.values())
        totals = endgame_totals(state)
        assert totals[TeamColor.RED] == totals[TeamColor.BLUE] == 3

    def test_push_moves_zone_along_real_lane(self):
        state = self._load_state()
        lane_id = "lane_1"
        lane = state.board.lanes[lane_id]
        bz = state.battle_zones[lane_id]
        idx = lane.index(bz)
        # Blue minion alone in lane_1's BZ -> red loses -> zone moves toward red base
        zone = state.board.zones[bz]
        a_hex = next(iter(zone.hexes))
        _add_minion(state, "b1", TeamColor.BLUE, lane_id, at=a_hex)
        _run_check(state)
        assert state.winner is None
        assert state.battle_zones[lane_id] == lane[idx - 1]
        assert state.wave_counters[lane_id] == 6
        # the other lane untouched
        assert state.battle_zones["lane_2"] == state.board.starting_battle_zones["lane_2"]
```

- [x] **Step 2: Run it**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_double_lane_endgame.py -q`
Expected: all pass. If `test_push_moves_zone_along_real_lane` fails because the chosen hex is occupied/terrain, pick an empty hex from the zone (`h for h in zone.hexes if not state.board.get_tile(h).is_terrain`).

- [x] **Step 3: Commit**

```bash
git add tests/engine/test_double_lane_endgame.py
git commit -m "test: double-lane endgame integration on Across the River map"
```

---

### Task 5: Lane-bound Necromancy/Necromastery (hex-first)

**Files:**
- Modify: `src/goa2/engine/steps/combat.py` (`RespawnMinionAtHexStep`, ~lines 972–1061)
- Modify: `src/goa2/scripts/dodger_effects.py` (`_build_respawn_steps`, ~lines 802–882)
- Test: `tests/engine/test_lane_respawn_binding.py` (new file)

**Interfaces:**
- Consumes: `state.lane_of_zone(zone_id) -> str | None`, `state.has_board_presence(id)`, existing hex filters (`SpawnPointTeamFilter`, `BattleZoneFilter`, `ObstacleFilter`, `RangeFilter`), `create_input_request`.
- Produces: `RespawnMinionAtHexStep(team=..., lane_bound=True, hex_filters=[...])` — hex-first flow with lane-bound minion supply. Legacy `unit_key` mode preserved (`unit_key: str | None = None`).

**Rulings encoded here (from the spec):**
- The minion supply is bound to the *chosen hex's lane*.
- Hexes whose lane has no limbo supply are not offered.
- Hexes outside any lane (possible under Dodger's Tide of Darkness, which makes all spaces spawn points) fall back to the full limbo supply — the binding rule cannot resolve a lane for a non-lane hex.

- [x] **Step 1: Write the failing tests**

Create `tests/engine/test_lane_respawn_binding.py`:

```python
"""Lane-bound ability respawns (Necromancy/Necromastery, hex-first).

Rulebook: minions are bound to the Battle Zone they originally spawned in
"for the purpose of respawning" — an ability respawn at a spawn point in
lane X's Battle Zone must consume lane X's limbo supply.
Spec: docs/superpowers/specs/2026-07-05-double-lane-endgame-design.md
"""

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import Hero, Minion, MinionType, Team, TeamColor
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.domain.types import UnitID
from goa2.engine.filters import (
    BattleZoneFilter,
    ObstacleFilter,
    RangeFilter,
    SpawnPointTeamFilter,
)
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import RespawnMinionAtHexStep


def _hex(q: int, r: int) -> Hex:
    return Hex(q=q, r=r, s=-q - r)


def _make_compact_two_lane_state() -> GameState:
    """Two 3-zone lanes on adjacent rows so one hero can reach both BZs.

    Row r=0 is lane_1 (rbase | mid | bbase), row r=2 is lane_2. A
    connector hex at (0,1) joins the rows and hosts the acting hero
    (RangeFilter measures from the current actor, so an actor MUST be
    set). Each mid zone has a RED minion spawn point; the spawn hexes
    (0,0) and (0,2) are both adjacent to the hero.
    """
    board = Board()
    lanes: dict[str, list[str]] = {}
    for lane_key, r in (("l1", 0), ("l2", 2)):
        zone_ids = [f"{lane_key}_{n}" for n in ("rbase", "mid", "bbase")]
        lanes[f"lane_{lane_key[-1]}"] = zone_ids
        board.zones[zone_ids[0]] = Zone(id=zone_ids[0], hexes=set())
        board.zones[zone_ids[2]] = Zone(id=zone_ids[2], hexes=set())
        hexes = [_hex(q, r) for q in range(0, 3)]
        board.zones[zone_ids[1]] = Zone(
            id=zone_ids[1],
            hexes=set(hexes),
            spawn_points=[
                SpawnPoint(
                    location=hexes[0],
                    team=TeamColor.RED,
                    type=SpawnType.MINION,
                    minion_type=MinionType.MELEE,
                ),
            ],
        )
        for h in hexes:
            tile = Tile(hex=h, zone_id=zone_ids[1])
            tile.spawn_point = SpawnPoint(
                location=h,
                team=TeamColor.RED,
                type=SpawnType.MINION,
                minion_type=MinionType.MELEE,
            )
            board.tiles[h] = tile
    # connector column between the rows (no zone, plain tiles)
    for r in (1,):
        for q in (0,):
            h = _hex(q, r)
            board.tiles[h] = Tile(hex=h)
    board.lanes = lanes

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )
    state.battle_zones = {"lane_1": "l1_mid", "lane_2": "l2_mid"}
    state.wave_counters = {"lane_1": 5, "lane_2": 5}

    hero = Hero(id="hero_dodger", name="Dodger", team=TeamColor.RED, deck=[], level=1)
    state.teams[TeamColor.RED].heroes.append(hero)
    state.place_entity("hero_dodger", _hex(0, 1))
    state.current_actor_id = "hero_dodger"
    return state


def _add_limbo_minion(state, minion_id, lane_id, minion_type=MinionType.MELEE):
    m = Minion(
        id=UnitID(minion_id), name=minion_id, team=TeamColor.RED,
        type=minion_type, lane_id=lane_id,
    )
    state.teams[TeamColor.RED].minions.append(m)
    return m


def _respawn_step() -> RespawnMinionAtHexStep:
    return RespawnMinionAtHexStep(
        team=TeamColor.RED,
        lane_bound=True,
        hex_filters=[
            SpawnPointTeamFilter(relation="FRIENDLY"),
            BattleZoneFilter(),
            ObstacleFilter(is_obstacle=False),
            RangeFilter(max_range=4),
        ],
    )


def _hex_option_ids(request) -> set[str]:
    return {opt.id for opt in request.options}


class TestLaneBoundRespawn:
    def test_only_lanes_with_supply_are_offered(self):
        state = _make_compact_two_lane_state()
        _add_limbo_minion(state, "red_l1", "lane_1")  # lane_2 has no supply

        push_steps(state, [_respawn_step()])
        result = process_stack(state)

        assert result.input_request is not None
        assert result.input_request.request_type == InputRequestType.SELECT_HEX
        ids = _hex_option_ids(result.input_request)
        assert "hex_0_0_0" in ids      # lane_1 spawn hex offered
        assert "hex_0_2_-2" not in ids  # lane_2 has no limbo supply

    def test_single_candidate_auto_places_from_hex_lane(self):
        state = _make_compact_two_lane_state()
        _add_limbo_minion(state, "red_l1", "lane_1")
        _add_limbo_minion(state, "red_l2", "lane_2")

        push_steps(state, [_respawn_step()])
        result = process_stack(state)
        assert result.input_request.request_type == InputRequestType.SELECT_HEX
        # choose the lane_2 spawn hex
        state.execution_stack[-1].pending_input = {"selection": {"q": 0, "r": 2, "s": -2}}
        result = process_stack(state)

        assert result.input_request is None
        # the LANE_2 minion was consumed, not lane_1's
        assert state.unit_locations.get("red_l2") == _hex(0, 2)
        assert "red_l1" not in state.unit_locations

    def test_multiple_types_prompt_choice_within_lane(self):
        state = _make_compact_two_lane_state()
        _add_limbo_minion(state, "red_l1_melee", "lane_1", MinionType.MELEE)
        _add_limbo_minion(state, "red_l1_ranged", "lane_1", MinionType.RANGED)
        _add_limbo_minion(state, "red_l2", "lane_2")

        push_steps(state, [_respawn_step()])
        result = process_stack(state)
        state.execution_stack[-1].pending_input = {"selection": {"q": 0, "r": 0, "s": 0}}
        result = process_stack(state)

        # two types in lane_1 -> minion choice, restricted to lane_1 supply
        assert result.input_request is not None
        assert result.input_request.request_type == InputRequestType.SELECT_OPTION
        option_ids = {opt.id for opt in result.input_request.options}
        assert option_ids == {"red_l1_melee", "red_l1_ranged"}

        state.execution_stack[-1].pending_input = {"selection": "red_l1_ranged"}
        result = process_stack(state)
        assert result.input_request is None
        assert state.unit_locations.get("red_l1_ranged") == _hex(0, 0)

    def test_no_supply_anywhere_finishes_without_input(self):
        state = _make_compact_two_lane_state()
        push_steps(state, [_respawn_step()])
        result = process_stack(state)
        assert result.input_request is None

    def test_lane_bound_step_round_trips_serialization(self):
        state = _make_compact_two_lane_state()
        push_steps(state, [_respawn_step()])
        data = state.model_dump(mode="json")
        restored = GameState.model_validate(data)
        s = restored.execution_stack[0]
        assert type(s).__name__ == "RespawnMinionAtHexStep"
        assert s.lane_bound is True
        assert s.unit_key is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_lane_respawn_binding.py -q`
Expected: FAIL — `lane_bound` unexpected keyword / validation error

- [x] **Step 3: Extend `RespawnMinionAtHexStep`**

In `src/goa2/engine/steps/combat.py`, replace the class. The legacy body moves into `_resolve_legacy` **unchanged**; the new lane-bound flow is added:

```python
_LANE_RESPAWN_HEX_KEY = "lane_respawn_hex"


class RespawnMinionAtHexStep(GameStep):
    """
    Respawns a minion at a hex chosen from filtered candidates.

    Two modes:
    - Legacy (unit_key set): the minion was chosen upstream; this step only
      picks the hex.
    - Lane-bound (lane_bound=True): hex-first. The player picks a spawn
      hex (only hexes whose lane has limbo supply are offered), then the
      minion comes from THAT lane's limbo supply (auto-picked when only
      one type is available). Hexes outside any lane (e.g. Tide of
      Darkness spawn points) fall back to the full limbo supply.

    Emits UNIT_PLACED event.
    """

    type: StepType = StepType.RESPAWN_MINION_AT_HEX
    team: TeamColor
    unit_key: str | None = None  # Context key containing minion ID (legacy mode)
    lane_bound: bool = False
    hex_filters: list[FilterCondition] = Field(default_factory=list)

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)
        if self.lane_bound:
            return self._resolve_lane_bound(state, context)
        return self._resolve_legacy(state, context)

    # ------------------------------------------------------------------
    # Legacy mode (unit_key): EXACTLY the previous resolve body, with the
    # initial should_skip check removed (done in resolve) and a guard:
    # ------------------------------------------------------------------
    def _resolve_legacy(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if not self.unit_key:
            logger.debug("   [RESPAWN] No unit_key configured.")
            return StepResult(is_finished=True)
        minion_id = context.get(self.unit_key)
        # ... (rest of the previous resolve body, unchanged)

    # ------------------------------------------------------------------
    # Lane-bound mode
    # ------------------------------------------------------------------
    def _limbo_minions_for_hex(self, state: GameState, team_obj, h: Hex) -> list:
        """Limbo minions legal at hex h: bound to the hex's lane, one per
        type. Hexes outside any lane fall back to all limbo minions."""
        tile = state.board.get_tile(h)
        lane_id = state.lane_of_zone(tile.zone_id) if tile and tile.zone_id else None
        seen: set = set()
        result = []
        for m in team_obj.minions:
            if state.has_board_presence(str(m.id)):
                continue
            if lane_id is not None and m.lane_id != lane_id:
                continue
            if m.type in seen:
                continue
            seen.add(m.type)
            result.append(m)
        return result

    def _place_minion(self, state: GameState, minion, selected_hex: Hex) -> StepResult:
        tile = state.board.get_tile(selected_hex)
        if tile and tile.is_occupied:
            logger.debug(f"   [ERROR] Cannot respawn {minion.id} at {selected_hex}. Occupied.")
            return StepResult(is_finished=True)
        state.move_unit(UnitID(minion.id), selected_hex)
        logger.debug(f"   [RESPAWN] Respawned {minion.id} at {selected_hex}")
        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.UNIT_PLACED,
                    actor_id=str(minion.id),
                    from_hex=None,
                    to_hex=_hex_dict(selected_hex),
                )
            ],
        )

    def _resolve_lane_bound(self, state: GameState, context: dict[str, Any]) -> StepResult:
        team_obj = state.teams.get(self.team)
        if not team_obj:
            return StepResult(is_finished=True)

        stored_hex = context.get(_LANE_RESPAWN_HEX_KEY)

        if self.pending_input:
            selection = self.pending_input.get("selection")

            # Round 1 answer: the hex.
            if stored_hex is None and isinstance(selection, dict):
                hex_obj = Hex(**selection)
                candidates = self._limbo_minions_for_hex(state, team_obj, hex_obj)
                if not candidates:
                    logger.debug("   [RESPAWN] No limbo supply for chosen hex's lane.")
                    return StepResult(is_finished=True)
                if len(candidates) == 1:
                    return self._place_minion(state, candidates[0], hex_obj)
                context[_LANE_RESPAWN_HEX_KEY] = selection
                return StepResult(
                    requires_input=True,
                    input_request=create_input_request(
                        request_type=InputRequestType.SELECT_OPTION,
                        player_id=(
                            str(state.current_actor_id) if state.current_actor_id else "system"
                        ),
                        prompt="Choose a minion to respawn.",
                        options=[
                            {"id": str(m.id), "text": f"{m.type.value} Minion"}
                            for m in candidates
                        ],
                    ),
                )

            # Round 2 answer: the minion.
            if stored_hex is not None and isinstance(selection, str):
                hex_obj = Hex(**stored_hex)
                context.pop(_LANE_RESPAWN_HEX_KEY, None)
                minion = next(
                    (
                        m
                        for m in self._limbo_minions_for_hex(state, team_obj, hex_obj)
                        if str(m.id) == selection
                    ),
                    None,
                )
                if not minion:
                    logger.debug(f"   [RESPAWN] Minion {selection} not available.")
                    return StepResult(is_finished=True)
                return self._place_minion(state, minion, hex_obj)

        # Round 0: offer spawn hexes whose lane has available supply.
        valid_hexes = []
        for h, tile in state.board.tiles.items():
            if tile.is_occupied:
                continue
            if not all(f.apply(h, state, context) for f in self.hex_filters):
                continue
            if not self._limbo_minions_for_hex(state, team_obj, h):
                continue
            valid_hexes.append(h)

        if not valid_hexes:
            logger.debug("   [RESPAWN] No valid lane-bound respawn hexes.")
            return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_HEX,
                player_id=(str(state.current_actor_id) if state.current_actor_id else "system"),
                prompt="Select space to respawn a minion.",
                options=valid_hexes,
            ),
        )
```

When moving the legacy body into `_resolve_legacy`, copy it verbatim from the current `resolve` (lines 989–1061) — only the `should_skip` check at the top is removed (now in `resolve`).

- [x] **Step 4: Rewrite `_build_respawn_steps` in dodger_effects.py**

Replace the whole function (lines 802–882):

```python
def _build_respawn_steps(
    state: GameState,
    hero: Hero,
    stats: CardStats,
    max_range: int,
) -> list[GameStep]:
    """
    Shared logic for Necromancy/Necromastery: hex-first respawn. The player
    picks a spawn-point hex in a Battle Zone in range; the minion comes
    from that hex's lane-bound limbo supply (rulebook: minions are bound to
    their original Battle Zone for the purpose of respawning).
    """
    if hero.team is None:
        return []
    team_obj = state.teams.get(hero.team)
    if not team_obj:
        return []
    if not any(not state.has_board_presence(str(m.id)) for m in team_obj.minions):
        return []

    return [
        RespawnMinionAtHexStep(
            team=hero.team,
            lane_bound=True,
            hex_filters=[
                SpawnPointTeamFilter(relation="FRIENDLY"),
                BattleZoneFilter(),
                ObstacleFilter(is_obstacle=False),
                RangeFilter(max_range=max_range),
            ],
        )
    ]
```

Remove imports that become unused in `dodger_effects.py` (`SetContextFlagStep`, `CheckContextConditionStep`, `SelectStep`, `TargetType` — **only if** nothing else in the file uses them; check with `uv run ruff check src/goa2/scripts/dodger_effects.py`).

- [x] **Step 5: Run the new tests and dodger regressions**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_lane_respawn_binding.py tests/engine/test_dodger_tide_of_darkness.py tests/engine/test_dodger_darkest_ritual.py tests/engine/effects/cases/test_dodger_effects.py tests/engine/test_steps_package_guardrails.py -q`
Expected: all pass. If a Tide of Darkness test exercises Necromancy/Necromastery with the old minion-first flow, update its input sequence to hex-first (the legality is unchanged).

- [x] **Step 6: Commit**

```bash
git add src/goa2/engine/steps/combat.py src/goa2/scripts/dodger_effects.py tests/engine/test_lane_respawn_binding.py
git commit -m "feat: lane-bound hex-first respawn for Necromancy/Necromastery"
```

---

### Task 6: Docs refresh + full regression

**Files:**
- Modify: `docs/DOUBLE_LANE_PREP.md`
- Modify: `src/goa2/engine/steps/combat.py` (only if the TBD comment survived Task 2)

**Interfaces:** none (documentation + verification).

- [x] **Step 1: Update `docs/DOUBLE_LANE_PREP.md`**

In the "Still TBD" section:
- Item 1 (map JSON + loader): mark done — loader reads a top-level `"lanes"` key (commit `fbfc67f`); `accross_the_river.json` is a real two-lane map (6 zones per lane, per-lane `battle_zones` starting positions); the browser map editor produces this format.
- Item 2 (endgame rules): mark done — describe the coordinator (`CheckLanePushStep`): throne precedence, post-push zone-count comparison via `map_logic.endgame_totals`, tie remedy (zones stay, counters stay flipped, full respawn in triggered lanes), every push re-compares once any lane's counters are exhausted. Reference the spec `docs/superpowers/specs/2026-07-05-double-lane-endgame-design.md`.
- Item 4 (simultaneous minion battles): note that pushes triggered by the same check now ARE resolved simultaneously by the coordinator; battle *removals* still resolve in lane order (unchanged, still unobservable).
- Add under "What was done": ability respawns (Necromancy/Necromastery) are lane-bound, hex-first.
- Leave items 3 (8–10 player setup config) and 6 (client rendering) as TBD.

Also verify the `NOTE (double-lane TBD)` comment in `engine/steps/combat.py` was replaced in Task 2 (`grep -n "double-lane TBD" src/goa2/engine/steps/combat.py` → no matches).

- [x] **Step 2: Run the full suite and linters**

Run: `PYTHONPATH=src uv run pytest tests/ -q`
Expected: all pass (~700+ tests).

Run: `uv run ruff check src/ && uv run black --check src/ && uv run mypy src/`
Expected: clean (fix any issues).

- [x] **Step 3: Commit**

```bash
git add docs/DOUBLE_LANE_PREP.md
git commit -m "docs: double-lane endgame shipped; refresh prep status"
```
