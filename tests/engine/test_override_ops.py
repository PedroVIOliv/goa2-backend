"""Override op registry: patch ops, atomicity, multi-piece conventions."""

import pytest

from goa2.domain.hex import Hex
from goa2.engine.overrides import (
    OVERRIDE_OPS,
    OverrideRejectedError,
    apply_override_decision,
    summarize_op,
)
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup

MAP_PATH = "src/goa2/data/maps/forgotten_island.json"


@pytest.fixture
def session() -> GameSession:
    state = GameSetup.create_game(MAP_PATH, ["Arien"], ["Wasp"], False, "QUICK", seed=42)
    return GameSession(state)


def _hex_dict(h: Hex) -> dict:
    return {"q": h.q, "r": h.r, "s": h.s}


def _free_adjacent(state, entity_id: str) -> Hex:
    pos = state.get_position(entity_id)
    for n in pos.neighbors():
        tile = state.board.tiles.get(n)
        if tile is not None and tile.occupant_id is None:
            return n
    raise AssertionError("no free adjacent hex")


def test_registry_contains_all_patch_and_unstick_ops():
    expected = {
        "move_entity",
        "remove_entity",
        "place_entity",
        "set_life_counters",
        "set_gold",
        "set_level",
        "add_marker",
        "remove_marker",
        "add_effect",
        "remove_effect",
        "move_card",
        "set_wave_counter",
        "set_tie_breaker_team",
        "skip_input",
        "abort_action",
        "end_turn",
        "force_actor",
    }
    assert expected <= set(OVERRIDE_OPS)
    for op in OVERRIDE_OPS.values():
        assert op.family in ("patch", "unstick")
        assert op.label and op.description


def test_unknown_op_rejected(session):
    with pytest.raises(OverrideRejectedError) as exc:
        apply_override_decision(session, "teleport_everything", {})
    assert exc.value.code == "unknown_op"


def test_move_entity_moves_a_hero(session):
    state = session.state
    target = _free_adjacent(state, "hero_arien")
    apply_override_decision(
        session, "move_entity", {"entity_id": "hero_arien", "hex": _hex_dict(target)}
    )
    assert session.state.get_position("hero_arien") == target
    # occupancy cache rebuilt
    assert str(session.state.board.tiles[target].occupant_id) == "hero_arien"


def test_move_entity_to_occupied_hex_rejected_and_commits_nothing(session):
    state = session.state
    arien_pos = state.get_position("hero_arien")
    wasp_pos = state.get_position("hero_wasp")
    with pytest.raises(OverrideRejectedError):
        apply_override_decision(
            session, "move_entity", {"entity_id": "hero_arien", "hex": _hex_dict(wasp_pos)}
        )
    assert session.state.get_position("hero_arien") == arien_pos
    assert session.state.get_position("hero_wasp") == wasp_pos


def test_move_entity_off_map_rejected(session):
    with pytest.raises(OverrideRejectedError):
        apply_override_decision(
            session,
            "move_entity",
            {"entity_id": "hero_arien", "hex": {"q": 99, "r": -99, "s": 0}},
        )


def test_remove_then_place_entity_round_trips(session):
    state = session.state
    pos = state.get_position("hero_wasp")
    apply_override_decision(session, "remove_entity", {"entity_id": "hero_wasp"})
    assert session.state.get_position("hero_wasp") is None
    apply_override_decision(
        session, "place_entity", {"entity_id": "hero_wasp", "hex": _hex_dict(pos)}
    )
    assert session.state.get_position("hero_wasp") == pos


def test_place_unknown_entity_rejected(session):
    with pytest.raises(OverrideRejectedError):
        apply_override_decision(
            session, "place_entity", {"entity_id": "minion_999", "hex": {"q": 0, "r": 0, "s": 0}}
        )


def test_move_entity_multi_piece_hero_requires_piece_id():
    state = GameSetup.create_game(MAP_PATH, ["Razzle"], ["Wasp"], False, "QUICK", seed=7)
    session = GameSession(state)
    pieces = state.get_piece_ids("hero_razzle")
    assert pieces, "expected Razzle pieces on the board"
    if len(pieces) > 1:
        with pytest.raises(OverrideRejectedError) as exc:
            apply_override_decision(
                session,
                "move_entity",
                {"entity_id": "hero_razzle", "hex": {"q": 0, "r": 0, "s": 0}},
            )
        assert "piece" in exc.value.message.lower()
    # Moving an explicit piece works
    piece = pieces[0]
    target = _free_adjacent(state, piece)
    apply_override_decision(session, "move_entity", {"entity_id": piece, "hex": _hex_dict(target)})
    assert session.state.get_position(piece) == target


def test_summarize_op_is_human_readable():
    text = summarize_op("move_entity", {"entity_id": "minion_4", "hex": {"q": 1, "r": -2, "s": 1}})
    assert "minion_4" in text
