"""Double-lane preparation: lane-aware state plumbing.

Covers:
- Legacy single-lane back-compat (Board.lane, GameState.active_zone_id /
  wave_counter) including old-save migration.
- Minion lane binding (respawn / return-to-zone / heavy immunity).
- Per-lane push checks and wave counters on a synthetic two-lane board.
- The convention that effect scripts never read the legacy single-lane fields.
"""

import glob
import os

import pytest

from goa2.domain.board import DEFAULT_LANE_ID, Board, Zone
from goa2.domain.factory import EntityFactory
from goa2.domain.hex import Hex
from goa2.domain.models import Minion, MinionType, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.domain.types import UnitID
from goa2.engine.filters_hex import BattleZoneFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.rules import is_immune
from goa2.engine.steps import CheckLanePushStep, RespawnMinionStep, ReturnMinionToZoneStep


def _minion(id_str: str, team: TeamColor, m_type=MinionType.MELEE, lane_id=DEFAULT_LANE_ID):
    return Minion(id=UnitID(id_str), name=id_str, team=team, type=m_type, lane_id=lane_id)


def _row_hexes(q_start: int, q_end: int, r: int) -> list[Hex]:
    return [Hex(q=q, r=r, s=-q - r) for q in range(q_start, q_end + 1)]


def _make_two_lane_state() -> GameState:
    """Two disconnected 5-zone lanes (one hex row each, 2 hexes per mid/beach zone)."""
    board = Board()
    zone_rows = {"l1": 0, "l2": 4}
    lanes: dict[str, list[str]] = {}

    for lane_key, r in zone_rows.items():
        zone_ids = [f"{lane_key}_{name}" for name in ("rbase", "rbeach", "mid", "bbeach", "bbase")]
        lanes[f"lane_{lane_key[-1]}"] = zone_ids
        # rbase gets no hexes (throne); the middle three zones get 2 hexes each
        board.zones[zone_ids[0]] = Zone(id=zone_ids[0], hexes=set())
        board.zones[zone_ids[4]] = Zone(id=zone_ids[4], hexes=set())
        q = 0
        for zone_id in zone_ids[1:4]:
            hexes = _row_hexes(q, q + 1, r)
            board.zones[zone_id] = Zone(id=zone_id, hexes=set(hexes))
            for h in hexes:
                board.tiles[h] = Tile(hex=h, zone_id=zone_id)
            q += 2

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
    return state


# =============================================================================
# Legacy single-lane back-compat
# =============================================================================


class TestBoardLaneBackCompat:
    def test_legacy_lane_kwarg_migrates_to_lanes(self):
        board = Board(lane=["a", "b", "c"])
        assert board.lanes == {DEFAULT_LANE_ID: ["a", "b", "c"]}
        assert board.lane == ["a", "b", "c"]

    def test_lane_setter_writes_lanes(self):
        board = Board()
        board.lane = ["a", "b", "c"]
        assert board.lanes == {DEFAULT_LANE_ID: ["a", "b", "c"]}

    def test_lane_property_raises_on_multi_lane(self):
        board = Board(lanes={"lane_1": ["a"], "lane_2": ["b"]})
        with pytest.raises(RuntimeError, match="multiple lanes"):
            _ = board.lane

    def test_lane_of_zone(self):
        board = Board(lanes={"lane_1": ["a", "b"], "lane_2": ["c", "d"]})
        assert board.lane_of_zone("d") == "lane_2"
        assert board.lane_of_zone("missing") is None


class TestGameStateLaneBackCompat:
    def _minimal_state(self, **kwargs) -> GameState:
        return GameState(
            board=Board(),
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
            **kwargs,
        )

    def test_legacy_kwargs_migrate(self):
        state = self._minimal_state(active_zone_id="z_mid", wave_counter=3)
        assert state.battle_zones == {DEFAULT_LANE_ID: "z_mid"}
        assert state.wave_counters == {DEFAULT_LANE_ID: 3}
        assert state.active_zone_id == "z_mid"
        assert state.wave_counter == 3

    def test_legacy_property_setters(self):
        state = self._minimal_state()
        state.active_zone_id = "z_new"
        state.wave_counter = 2
        assert state.battle_zones == {DEFAULT_LANE_ID: "z_new"}
        assert state.wave_counters == {DEFAULT_LANE_ID: 2}

    def test_defaults_match_old_behavior(self):
        state = self._minimal_state()
        assert state.active_zone_id is None
        assert state.wave_counter == 5

    def test_legacy_save_json_migrates(self):
        state = self._minimal_state(active_zone_id="z_mid", wave_counter=4)
        data = state.model_dump(mode="json")
        # Simulate a pre-lanes save file
        data.pop("battle_zones")
        data.pop("wave_counters")
        data["active_zone_id"] = "z_mid"
        data["wave_counter"] = 4
        loaded = GameState.model_validate(data)
        assert loaded.battle_zones == {DEFAULT_LANE_ID: "z_mid"}
        assert loaded.wave_counters == {DEFAULT_LANE_ID: 4}

    def test_multi_lane_round_trips(self):
        state = _make_two_lane_state()
        loaded = GameState.model_validate(state.model_dump(mode="json"))
        assert loaded.battle_zones == {"lane_1": "l1_mid", "lane_2": "l2_mid"}
        assert loaded.wave_counters == {"lane_1": 5, "lane_2": 5}
        assert loaded.board.lanes.keys() == {"lane_1", "lane_2"}

    def test_legacy_accessors_raise_on_multi_lane(self):
        state = _make_two_lane_state()
        with pytest.raises(RuntimeError, match="multiple"):
            _ = state.active_zone_id
        with pytest.raises(RuntimeError, match="multiple"):
            _ = state.wave_counter
        with pytest.raises(RuntimeError, match="multiple"):
            state.active_zone_id = "z"
        with pytest.raises(RuntimeError, match="multiple"):
            state.wave_counter = 1

    def test_lane_helpers(self):
        state = _make_two_lane_state()
        assert state.battle_zone_ids() == {"l1_mid", "l2_mid"}
        assert state.battle_zone_for_lane("lane_2") == "l2_mid"
        assert state.lane_of_zone("l2_mid") == "lane_2"
        assert state.lane_of_zone("l1_rbeach") == "lane_1"


# =============================================================================
# Minion lane binding
# =============================================================================


class TestMinionLaneBinding:
    def test_default_lane_id(self):
        m = Minion(id=UnitID("m1"), name="m1", team=TeamColor.RED, type=MinionType.MELEE)
        assert m.lane_id == DEFAULT_LANE_ID

    def test_factory_binds_lane(self):
        state = _make_two_lane_state()
        m = EntityFactory.create_minion(state, TeamColor.RED, MinionType.MELEE, "lane_2")
        assert m.lane_id == "lane_2"
        default = EntityFactory.create_minion(state, TeamColor.RED, MinionType.MELEE)
        assert default.lane_id == DEFAULT_LANE_ID

    def test_respawn_only_uses_minions_of_that_lane(self):
        state = _make_two_lane_state()
        # A limbo minion bound to lane_1 must not respawn via a lane_2 respawn
        limbo = _minion("r1", TeamColor.RED, lane_id="lane_1")
        state.teams[TeamColor.RED].minions.append(limbo)

        push_steps(
            state,
            [RespawnMinionStep(team=TeamColor.RED, minion_type=MinionType.MELEE, lane_id="lane_2")],
        )
        result = process_stack(state)
        assert result.input_request is None
        assert limbo.id not in state.unit_locations

        # The matching lane asks where to place it
        push_steps(
            state,
            [RespawnMinionStep(team=TeamColor.RED, minion_type=MinionType.MELEE, lane_id="lane_1")],
        )
        result = process_stack(state)
        assert result.input_request is not None

    def test_return_minion_goes_to_own_lane_battle_zone(self):
        state = _make_two_lane_state()
        stray = _minion("b1", TeamColor.BLUE, lane_id="lane_2")
        state.teams[TeamColor.BLUE].minions.append(stray)
        # Place it in lane_2's red beach (outside l2_mid)
        state.move_unit(stray.id, Hex(q=1, r=4, s=-5))

        push_steps(state, [ReturnMinionToZoneStep()])
        process_stack(state)

        loc = state.unit_locations[stray.id]
        assert loc in state.board.zones["l2_mid"].hexes

    def test_heavy_immunity_scoped_to_own_lane(self):
        state = _make_two_lane_state()
        heavy = _minion("h1", TeamColor.RED, m_type=MinionType.HEAVY, lane_id="lane_1")
        escort = _minion("e1", TeamColor.RED, lane_id="lane_1")
        state.teams[TeamColor.RED].minions.extend([heavy, escort])
        state.move_unit(heavy.id, Hex(q=2, r=0, s=-2))
        state.move_unit(escort.id, Hex(q=3, r=0, s=-3))

        assert is_immune(heavy, state) is True

        # A protector bound to another lane does not grant immunity,
        # even if it physically stands in the heavy's battle zone.
        escort.lane_id = "lane_2"
        assert is_immune(heavy, state) is False


# =============================================================================
# Per-lane push checks
# =============================================================================


class TestTwoLanePush:
    def test_check_lane_push_covers_all_lanes_and_pushes_only_triggered_lane(self):
        state = _make_two_lane_state()
        # lane_1: contested (no push). lane_2: red has 0 minions -> blue pushes.
        r1 = _minion("r1", TeamColor.RED, lane_id="lane_1")
        b1 = _minion("b1", TeamColor.BLUE, lane_id="lane_1")
        b2 = _minion("b2", TeamColor.BLUE, lane_id="lane_2")
        state.teams[TeamColor.RED].minions.append(r1)
        state.teams[TeamColor.BLUE].minions.extend([b1, b2])
        state.move_unit(r1.id, Hex(q=2, r=0, s=-2))
        state.move_unit(b1.id, Hex(q=3, r=0, s=-3))
        state.move_unit(b2.id, Hex(q=2, r=4, s=-6))

        push_steps(state, [CheckLanePushStep()])
        process_stack(state)

        # lane_2 pushed toward Red; lane_1 untouched
        assert state.battle_zones == {"lane_1": "l1_mid", "lane_2": "l2_rbeach"}
        assert state.wave_counters == {"lane_1": 5, "lane_2": 4}
        # Old-zone minions of the pushed lane are wiped
        assert b2.id not in state.unit_locations
        # lane_1 minions are untouched
        assert r1.id in state.unit_locations
        assert b1.id in state.unit_locations

    def test_lane_scoped_check_ignores_other_lanes(self):
        state = _make_two_lane_state()
        b2 = _minion("b2", TeamColor.BLUE, lane_id="lane_2")
        state.teams[TeamColor.BLUE].minions.append(b2)
        state.move_unit(b2.id, Hex(q=2, r=4, s=-6))

        push_steps(state, [CheckLanePushStep(lane_id="lane_1")])
        process_stack(state)

        # lane_2 met the push condition but was not checked
        assert state.battle_zones["lane_2"] == "l2_mid"
        assert state.wave_counters["lane_2"] == 5


# =============================================================================
# Filters treat "the Battle Zone" as "a Battle Zone"
# =============================================================================


class TestBattleZoneFilterMultiLane:
    def test_hexes_in_any_battle_zone_pass(self):
        state = _make_two_lane_state()
        f = BattleZoneFilter()
        assert f.apply(Hex(q=2, r=0, s=-2), state, {}) is True  # l1_mid
        assert f.apply(Hex(q=2, r=4, s=-6), state, {}) is True  # l2_mid
        assert f.apply(Hex(q=0, r=0, s=0), state, {}) is False  # l1_rbeach


# =============================================================================
# Convention: effect scripts must not use legacy single-lane accessors
# =============================================================================


def test_effect_scripts_do_not_use_legacy_single_lane_accessors():
    """Effect scripts must go through battle_zones / battle_zone_ids() /
    battle_zone_for_lane() (or BattleZoneFilter) so they stay correct on
    multi-lane maps. The legacy properties raise there."""
    scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "src", "goa2", "scripts")
    offenders = []
    for path in glob.glob(os.path.join(scripts_dir, "*_effects.py")):
        with open(path) as f:
            source = f.read()
        for needle in (".active_zone_id", ".wave_counter"):
            if needle in source:
                offenders.append(f"{os.path.basename(path)}: {needle}")
    assert not offenders, (
        "Effect scripts must not use legacy single-lane accessors "
        f"(use lane-aware helpers instead): {offenders}"
    )
