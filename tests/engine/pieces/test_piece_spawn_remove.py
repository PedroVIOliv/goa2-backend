"""Spawn (supply-capped) and voluntary removal of hero pieces."""

from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.pieces import RemoveHeroPieceStep, SpawnHeroPieceStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _state(n_pieces: int) -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (0, 1, -1),
                (1, -1, 0),
                (-1, 1, 0),
                (-1, 0, 1),
            ]
        )
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    coords = [(0, 0, 0), (1, 0, -1), (0, 1, -1)]
    for i in range(n_pieces):
        q, r, s = coords[i]
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))
    return state


def test_spawn_up_to_three_capped_by_supply_and_hexes():
    state = _state(n_pieces=1)
    state.acting_piece_id = piece_id("hero_razzle", 1)
    push_steps(state, [SpawnHeroPieceStep(hero_id="hero_razzle", max_count=3, radius=1)])

    for _ in range(3):
        result = process_stack(state)
        assert result.input_request is not None
        first_hex = result.input_request.options[0].metadata["hex"]
        state.execution_stack[-1].pending_input = {"selection": first_hex}

    result = process_stack(state)
    assert result.input_request is None
    assert len(state.get_piece_ids("hero_razzle")) == 4


def test_spawn_is_skippable_per_piece():
    state = _state(n_pieces=1)
    state.acting_piece_id = piece_id("hero_razzle", 1)
    push_steps(state, [SpawnHeroPieceStep(hero_id="hero_razzle", max_count=3, radius=1)])

    result = process_stack(state)
    assert result.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": "SKIP"}
    result = process_stack(state)

    assert result.input_request is None
    assert len(state.get_piece_ids("hero_razzle")) == 1


def test_remove_one_piece_keeps_min_remaining():
    state = _state(n_pieces=2)
    push_steps(state, [RemoveHeroPieceStep(hero_id="hero_razzle", mode="choose_one")])
    result = process_stack(state)
    assert result.input_request is not None
    option_ids = {o.id for o in result.input_request.options}
    assert option_ids == {piece_id("hero_razzle", 1), piece_id("hero_razzle", 2), "SKIP"}

    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 1)}
    process_stack(state)

    assert piece_id("hero_razzle", 1) not in state.entity_locations
    assert state.has_board_presence("hero_razzle")
    assert "hero_razzle" not in state.heroes_defeated_this_round


def test_remove_choose_one_noop_with_single_piece():
    state = _state(n_pieces=1)
    push_steps(state, [RemoveHeroPieceStep(hero_id="hero_razzle", mode="choose_one")])
    result = process_stack(state)
    assert result.input_request is None
    assert state.has_board_presence("hero_razzle")


def test_remove_all_others_keeps_acting_piece():
    state = _state(n_pieces=3)
    state.acting_piece_id = piece_id("hero_razzle", 2)
    push_steps(state, [RemoveHeroPieceStep(hero_id="hero_razzle", mode="all_others")])
    result = process_stack(state)
    assert result.input_request is None
    assert state.get_piece_ids("hero_razzle") == [piece_id("hero_razzle", 2)]


def test_removed_pieces_return_to_supply_for_respawn():
    state = _state(n_pieces=2)
    push_steps(state, [RemoveHeroPieceStep(hero_id="hero_razzle", mode="choose_one")])
    result = process_stack(state)
    assert result.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    process_stack(state)

    from goa2.engine.hero_pieces import pieces_in_supply

    razzle = state.get_hero("hero_razzle")
    assert piece_id("hero_razzle", 2) in pieces_in_supply(state, razzle)
