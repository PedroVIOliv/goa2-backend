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
from goa2.engine.steps import LanePushStep


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
        id=UnitID(minion_id),
        name=minion_id,
        team=team,
        type=MinionType.MELEE,
        lane_id=lane_id,
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


class TestLanePushMechanicsOnly:
    def test_precomputed_push_skips_counter_and_endgame(self):
        state = _make_endgame_state(waves=1)
        _add_minion(
            state, "blue_1", TeamColor.BLUE, "lane_1", at=_row_hexes(4, 7, 0)[3]
        )  # in l1_mid
        _add_minion(state, "red_limbo", TeamColor.RED, "lane_1")  # limbo

        push_steps(
            state,
            [
                LanePushStep(
                    lane_id="lane_1",
                    losing_team=TeamColor.RED,
                    target_zone_id="l1_rbeach",
                    skip_wave_counter=True,
                )
            ],
        )
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
        push_steps(
            state,
            [
                LanePushStep(
                    lane_id="lane_2",
                    losing_team=TeamColor.BLUE,
                    target_zone_id="l2_bbeach",
                    skip_wave_counter=True,
                )
            ],
        )
        data = state.model_dump(mode="json")
        restored = GameState.model_validate(data)
        s = restored.execution_stack[0]
        assert type(s).__name__ == "LanePushStep"
        assert s.target_zone_id == "l2_bbeach"
        assert s.skip_wave_counter is True
