"""GameState position resolver for multi-piece heroes."""

from goa2.domain.hex import Hex
from goa2.domain.models.marker import MarkerType
from goa2.domain.state import GameState
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from tests.engine.effects.builders import EffectScenarioBuilder


def _state() -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    return state


def test_get_positions_returns_all_piece_hexes():
    state = _state()
    positions = state.get_positions("hero_razzle")
    assert set(positions) == {Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1)}


def test_get_positions_normal_hero():
    state = _state()
    assert state.get_positions("hero_knight") == [Hex(q=2, r=0, s=-2)]


def test_get_position_multi_piece_unbound_is_none():
    state = _state()
    assert state.get_position("hero_razzle") is None


def test_get_position_resolves_acting_piece():
    state = _state()
    state.acting_piece_id = piece_id("hero_razzle", 2)
    assert state.get_position("hero_razzle") == Hex(q=1, r=0, s=-1)


def test_get_position_piece_id_direct():
    state = _state()
    assert state.get_position(piece_id("hero_razzle", 1)) == Hex(q=0, r=0, s=0)


def test_has_board_presence():
    state = _state()
    assert state.has_board_presence("hero_razzle") is True
    state.remove_entity(piece_id("hero_razzle", 1))
    state.remove_entity(piece_id("hero_razzle", 2))
    assert state.has_board_presence("hero_razzle") is False
    assert state.has_board_presence("hero_knight") is True


def test_get_piece_ids():
    state = _state()
    assert state.get_piece_ids("hero_razzle") == [
        piece_id("hero_razzle", 1),
        piece_id("hero_razzle", 2),
    ]
    assert state.get_piece_ids("hero_knight") == ["hero_knight"]


def test_resolve_board_actor():
    state = _state()
    assert state.resolve_board_actor("hero_knight") == "hero_knight"
    state.acting_piece_id = piece_id("hero_razzle", 2)
    assert state.resolve_board_actor("hero_razzle") == piece_id("hero_razzle", 2)


def test_place_marker_on_piece_attaches_to_hero():
    state = _state()
    marker = state.place_marker(
        MarkerType.BOUNTY, target_id=piece_id("hero_razzle", 2), value=1, source_id="hero_knight"
    )
    assert marker.target_id == "hero_razzle"
    assert state.get_markers_on_hero("hero_razzle") == [marker]


def test_acting_piece_id_round_trips():
    state = _state()
    state.acting_piece_id = piece_id("hero_razzle", 1)
    restored = GameState.model_validate_json(state.model_dump_json())
    assert restored.acting_piece_id == piece_id("hero_razzle", 1)
