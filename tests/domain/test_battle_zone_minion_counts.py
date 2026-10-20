from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Minion, MinionType, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.views import build_view


def _state():
    board = Board(
        zones={
            name: Zone(id=name, hexes={Hex(q=q, r=-q, s=0)})
            for q, name in enumerate(("left", "right", "reserve"))
        }
    )
    board.populate_tiles_from_zones()
    heavy = Minion(id="heavy", name="Heavy", team=TeamColor.RED, type=MinionType.HEAVY)
    reserve = heavy.model_copy(update={"id": "reserve"})
    offboard = heavy.model_copy(update={"id": "offboard"})
    blue = heavy.model_copy(update={"id": "blue", "team": TeamColor.BLUE})
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, minions=[heavy, heavy, reserve, offboard]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, minions=[blue]),
        },
    )
    state.battle_zones = {"lane_1": "left", "lane_2": "right"}
    state.entity_locations = {
        "heavy": Hex(q=0, r=0, s=0),
        "blue": Hex(q=1, r=-1, s=0),
        "reserve": Hex(q=2, r=-2, s=0),
        "not_a_minion": Hex(q=0, r=0, s=0),
    }
    return state


def test_counts_are_physical_per_zone_and_public():
    state = _state()
    expected = {
        "lane_1": {"zone_id": "left", "counts": {"RED": 1, "BLUE": 0}},
        "lane_2": {"zone_id": "right", "counts": {"RED": 0, "BLUE": 1}},
    }
    assert build_view(state)["battle_zone_minion_counts"] == expected
    assert build_view(state, for_hero_id="unseated")["battle_zone_minion_counts"] == expected
    assert "battle_zone_minion_counts" not in state.model_dump(mode="json")


def test_counts_follow_movement_and_zone_changes_not_minion_lane_binding():
    state = _state()
    state.entity_locations["heavy"] = Hex(q=1, r=-1, s=0)
    counts = build_view(state)["battle_zone_minion_counts"]
    assert counts["lane_1"]["counts"] == {"RED": 0, "BLUE": 0}
    assert counts["lane_2"]["counts"] == {"RED": 1, "BLUE": 1}
    state.battle_zones["lane_1"] = "reserve"
    assert build_view(state)["battle_zone_minion_counts"]["lane_1"]["counts"]["RED"] == 1
    del state.entity_locations["heavy"]
    assert build_view(state)["battle_zone_minion_counts"]["lane_2"]["counts"]["RED"] == 0


def test_missing_zone_is_omitted_and_valid_empty_zone_has_zero_counts():
    state = _state()
    state.battle_zones = {"lane_1": "left", "lane_2": "missing"}
    state.entity_locations.clear()
    assert build_view(state)["battle_zone_minion_counts"] == {
        "lane_1": {"zone_id": "left", "counts": {"RED": 0, "BLUE": 0}}
    }
