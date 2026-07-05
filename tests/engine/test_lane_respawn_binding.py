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
        # One melee + one ranged spawn point per mid zone, so both types have
        # respawn headroom (the per-zone spawn-point cap gates by type/color).
        hex_types = [MinionType.MELEE, MinionType.RANGED, MinionType.MELEE]
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
                SpawnPoint(
                    location=hexes[1],
                    team=TeamColor.RED,
                    type=SpawnType.MINION,
                    minion_type=MinionType.RANGED,
                ),
            ],
        )
        for h, mt in zip(hexes, hex_types, strict=True):
            tile = Tile(hex=h, zone_id=zone_ids[1])
            tile.spawn_point = SpawnPoint(
                location=h,
                team=TeamColor.RED,
                type=SpawnType.MINION,
                minion_type=mt,
            )
            board.tiles[h] = tile
    # connector hex between the rows (no zone, plain tile)
    h = _hex(0, 1)
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
        id=UnitID(minion_id),
        name=minion_id,
        team=TeamColor.RED,
        type=minion_type,
        lane_id=lane_id,
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
        assert "hex_0_0_0" in ids  # lane_1 spawn hex offered
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


def _make_single_zone_state(
    *,
    melee_spawns: int = 1,
    ranged_spawns: int = 1,
) -> GameState:
    """One-lane, one-Battle-Zone board with distinct per-type spawn counts.

    Models the Forgotten Island trap: a zone whose count of spawn points of
    a given (type, color) is the real cap on how many minions of that type
    may be present there — independent of how many miniatures are bound to
    the lane. Spawn hexes lie on row r=0; the RED hero stands at the far end.
    """
    board = Board()
    zone_ids = ["mid_rbase", "mid", "mid_bbase"]
    board.lanes = {"lane_1": zone_ids}
    board.zones["mid_rbase"] = Zone(id="mid_rbase", hexes=set())
    board.zones["mid_bbase"] = Zone(id="mid_bbase", hexes=set())

    spawn_specs: list[tuple[Hex, MinionType]] = []
    col = 0
    for _ in range(melee_spawns):
        spawn_specs.append((_hex(col, 0), MinionType.MELEE))
        col += 1
    for _ in range(ranged_spawns):
        spawn_specs.append((_hex(col, 0), MinionType.RANGED))
        col += 1
    hero_hex = _hex(col, 0)  # first non-spawn hex

    spawn_points = [
        SpawnPoint(
            location=h,
            team=TeamColor.RED,
            type=SpawnType.MINION,
            minion_type=mt,
        )
        for h, mt in spawn_specs
    ]
    mid_hexes = [h for h, _ in spawn_specs] + [hero_hex]
    board.zones["mid"] = Zone(id="mid", hexes=set(mid_hexes), spawn_points=spawn_points)

    by_hex = {sp.location: sp for sp in spawn_points}
    for h in mid_hexes:
        tile = Tile(hex=h, zone_id="mid")
        tile.spawn_point = by_hex.get(h)
        board.tiles[h] = tile

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )
    state.battle_zones = {"lane_1": "mid"}
    state.wave_counters = {"lane_1": 5}

    hero = Hero(id="hero_dodger", name="Dodger", team=TeamColor.RED, deck=[], level=1)
    state.teams[TeamColor.RED].heroes.append(hero)
    state.place_entity("hero_dodger", hero_hex)
    state.current_actor_id = "hero_dodger"
    return state


def _place_minion(state, minion_id, at, lane_id="lane_1", minion_type=MinionType.MELEE):
    m = _add_limbo_minion(state, minion_id, lane_id, minion_type)
    state.place_entity(UnitID(minion_id), at)
    return m


class TestPerZoneSpawnCap:
    """Rulebook: may respawn a minion of (type, color) only if that zone has
    MORE spawn points of that (type, color) than miniatures of it present."""

    def test_capped_type_not_offered(self):
        # mid: 1 melee spawn (occupied), 1 ranged spawn (empty).
        state = _make_single_zone_state(melee_spawns=1, ranged_spawns=1)
        _place_minion(state, "red_melee_present", _hex(0, 0))  # fills the melee cap
        _add_limbo_minion(state, "red_melee_limbo", "lane_1", MinionType.MELEE)

        push_steps(state, [_respawn_step()])
        result = process_stack(state)

        # Melee is at capacity (1 spawn point, 1 present); the only limbo
        # minion is a melee, so no legal respawn exists -> no hex offered.
        assert result.input_request is None
        assert "red_melee_limbo" not in state.unit_locations

    def test_capped_type_excluded_uncapped_type_placed(self):
        # mid: 1 melee spawn (occupied), 1 ranged spawn (empty).
        state = _make_single_zone_state(melee_spawns=1, ranged_spawns=1)
        _place_minion(state, "red_melee_present", _hex(0, 0))
        _add_limbo_minion(state, "red_melee_limbo", "lane_1", MinionType.MELEE)
        _add_limbo_minion(state, "red_ranged_limbo", "lane_1", MinionType.RANGED)

        push_steps(state, [_respawn_step()])
        result = process_stack(state)
        assert result.input_request.request_type == InputRequestType.SELECT_HEX
        # choose the empty ranged spawn hex
        state.execution_stack[-1].pending_input = {"selection": {"q": 1, "r": 0, "s": -1}}
        result = process_stack(state)

        # Only the ranged is eligible -> auto-placed (no melee/ranged choice).
        assert result.input_request is None
        assert state.unit_locations.get("red_ranged_limbo") == _hex(1, 0)
        assert "red_melee_limbo" not in state.unit_locations  # melee stayed capped

    def test_headroom_allows_respawn(self):
        # mid: 1 melee spawn, EMPTY (no present melee) -> headroom exists.
        state = _make_single_zone_state(melee_spawns=1, ranged_spawns=0)
        _add_limbo_minion(state, "red_melee_limbo", "lane_1", MinionType.MELEE)

        push_steps(state, [_respawn_step()])
        result = process_stack(state)
        assert result.input_request.request_type == InputRequestType.SELECT_HEX
        state.execution_stack[-1].pending_input = {"selection": {"q": 0, "r": 0, "s": 0}}
        result = process_stack(state)

        assert result.input_request is None
        assert state.unit_locations.get("red_melee_limbo") == _hex(0, 0)
