"""Respawn semantics for multi-piece heroes."""

from goa2.domain.hex import Hex
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.combat import RespawnHeroStep
from tests.engine.effects.builders import EffectScenarioBuilder

_SPAWN_HEX = Hex(q=0, r=1, s=-1)


def _state(pieces_on_board: int) -> GameState:
    builder = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .spawn_point(at=(0, 1, -1), team="RED", spawn_type=SpawnType.HERO)
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
    )
    state = builder.build()
    # EffectScenarioBuilder.spawn_point() only records the SpawnPoint on the
    # tile; RespawnHeroStep reads the board-level list, so mirror it there too.
    state.board.spawn_points.append(
        SpawnPoint(location=_SPAWN_HEX, team="RED", type=SpawnType.HERO)
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    coords = [(0, 0, 0), (1, 0, -1)]
    for i in range(pieces_on_board):
        q, r, s = coords[i]
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))
    return state


def test_no_respawn_prompt_while_pieces_on_board():
    state = _state(pieces_on_board=1)
    push_steps(state, [RespawnHeroStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request is None  # step finished silently


def test_respawn_places_one_piece():
    state = _state(pieces_on_board=0)
    push_steps(state, [RespawnHeroStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request.request_type.value == "CHOOSE_RESPAWN"
    state.execution_stack[-1].pending_input = {"selection": "RESPAWN"}
    result = process_stack(state)
    assert result.input_request.request_type.value == "CHOOSE_RESPAWN_HEX"
    hex_option = result.input_request.options[0]
    state.execution_stack[-1].pending_input = {"selection": hex_option.metadata["hex"]}
    process_stack(state)
    assert piece_id("hero_razzle", 1) in state.entity_locations
    assert "hero_razzle" not in state.entity_locations
    assert state.has_board_presence("hero_razzle")
