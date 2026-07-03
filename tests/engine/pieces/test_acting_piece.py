"""Acting-piece binding: choice prompt, auto-bind, movement via the piece."""

from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.movement import MoveSequenceStep
from goa2.engine.steps.pieces import ChooseActingPieceStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _state(n_pieces: int) -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(3, 0, -3))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    coords = [(0, 0, 0), (1, 0, -1)]
    for i in range(n_pieces):
        q, r, s = coords[i]
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))
    return state


def test_single_piece_auto_binds_without_prompt():
    state = _state(n_pieces=1)
    push_steps(state, [ChooseActingPieceStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request is None
    assert state.acting_piece_id == piece_id("hero_razzle", 1)


def test_two_pieces_prompt_and_bind():
    state = _state(n_pieces=2)
    push_steps(state, [ChooseActingPieceStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.player_id == "hero_razzle"
    option_ids = {o.id for o in result.input_request.options}
    assert option_ids == {piece_id("hero_razzle", 1), piece_id("hero_razzle", 2)}

    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    process_stack(state)
    assert state.acting_piece_id == piece_id("hero_razzle", 2)


def test_normal_hero_is_noop():
    state = _state(n_pieces=1)
    push_steps(state, [ChooseActingPieceStep(hero_id="hero_knight")])
    result = process_stack(state)
    assert result.input_request is None
    assert state.acting_piece_id is None


def test_move_sequence_moves_the_bound_piece():
    state = _state(n_pieces=2)
    state.acting_piece_id = piece_id("hero_razzle", 2)
    push_steps(state, [MoveSequenceStep(unit_id="hero_razzle", range_val=1)])
    result = process_stack(state)
    assert result.input_request is not None

    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": 0, "s": -2}}
    process_stack(state)

    assert state.entity_locations[piece_id("hero_razzle", 2)] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations[piece_id("hero_razzle", 1)] == Hex(q=0, r=0, s=0)
