"""Attacking a piece routes defense to the owning player."""

from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.combat import AttackSequenceStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _state() -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    return state


def test_attacking_piece_prompts_owner_for_defense():
    state = _state()
    push_steps(state, [AttackSequenceStep(damage=4, range_val=1)])
    result = process_stack(state)
    # Target selection: pick the adjacent piece
    assert result.input_request.request_type.value == "SELECT_UNIT"
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    result = process_stack(state)
    # Defense window must be addressed to the OWNER hero (token routing)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_CARD_OR_PASS"
    assert result.input_request.player_id == "hero_razzle"
    # Positional truth: defender_id stays the piece
    assert state.execution_context["attacker_id"] == "hero_knight"


def test_defense_pass_defeats_and_defender_id_is_piece():
    state = _state()
    push_steps(state, [AttackSequenceStep(damage=4, range_val=1)])
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "PASS"}
    process_stack(state)
    assert state.execution_context["defender_id"] == piece_id("hero_razzle", 2)
