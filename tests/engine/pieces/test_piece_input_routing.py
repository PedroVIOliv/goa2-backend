"""Fix 2 guards: input prompts derived from piece IDs route to the owner hero."""

from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models.enums import TargetType
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.cards import ForceDiscardOrDefeatStep, ForceDiscardStep
from goa2.engine.steps.selection import (
    AskConfirmationStep,
    GuessCardColorStep,
    MultiSelectStep,
    SelectStep,
)
from tests.engine.effects.builders import EffectScenarioBuilder, skill_card


def _state(actor: str = "hero_knight") -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor(actor)
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    return state


def test_forced_discard_on_piece_shows_owner_hand_and_routes_to_owner():
    state = _state()
    razzle = state.get_hero("hero_razzle")
    razzle.hand = [skill_card("card_a"), skill_card("card_b")]
    state.execution_context["victim_id"] = piece_id("hero_razzle", 2)

    push_steps(
        state,
        [
            SelectStep(
                target_type=TargetType.CARD,
                prompt="Discard a card",
                output_key="discard_sel",
                is_mandatory=True,
                context_hero_id_key="victim_id",
                override_player_id_key="victim_id",
            )
        ],
    )
    result = process_stack(state)
    assert result.input_request is not None
    # The player who answers is Razzle, never a piece ID.
    assert result.input_request.player_id == "hero_razzle"
    # And the options come from Razzle's hand.
    option_ids = {o.id for o in result.input_request.options}
    assert option_ids == {"card_a", "card_b"}


def test_forced_discard_on_piece_logs_owner_hero_for_this_turn():
    state = _state()
    razzle = state.get_hero("hero_razzle")
    razzle.hand = [skill_card("card_a")]
    victim_piece = piece_id("hero_razzle", 2)
    state.execution_context["victim_id"] = victim_piece

    push_steps(state, [ForceDiscardStep(victim_key="victim_id")])
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.player_id == "hero_razzle"

    state.execution_stack[-1].pending_input = {"selection": "card_a"}
    result = process_stack(state)

    assert result.input_request is None
    assert state.turn_discard_log.get("hero_razzle") == ["card_a"]
    assert victim_piece not in state.turn_discard_log


def test_confirmation_step_with_piece_player_id_routes_to_owner():
    state = _state()
    push_steps(
        state,
        [
            AskConfirmationStep(
                prompt="Use passive?",
                player_id=piece_id("hero_razzle", 1),
            )
        ],
    )
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.player_id == "hero_razzle"


def test_default_select_with_piece_actor_routes_prompt_to_owner():
    state = _state(actor=piece_id("hero_razzle", 1))
    push_steps(
        state,
        [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose a number",
                output_key="number",
                number_options=[1, 2],
            )
        ],
    )
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.SELECT_NUMBER
    assert result.input_request.player_id == "hero_razzle"


def test_multiselect_with_piece_actor_routes_prompt_to_owner():
    state = _state(actor=piece_id("hero_razzle", 1))
    push_steps(
        state,
        [
            MultiSelectStep(
                target_type=TargetType.UNIT,
                prompt="Select units",
                output_key="targets",
                max_selections=1,
            )
        ],
    )
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.SELECT_UNIT
    assert result.input_request.player_id == "hero_razzle"


def test_guess_card_color_with_piece_actor_routes_prompt_to_owner():
    state = _state(actor=piece_id("hero_razzle", 1))
    push_steps(state, [GuessCardColorStep(output_key="guess")])
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.SELECT_OPTION
    assert result.input_request.player_id == "hero_razzle"


def test_discard_or_defeat_skips_stale_offboard_piece_victim():
    state = _state()
    razzle = state.get_hero("hero_razzle")
    razzle.hand = [skill_card("card_a")]
    stale_piece = piece_id("hero_razzle", 2)
    state.remove_entity(stale_piece)
    state.execution_context["victim_id"] = stale_piece

    push_steps(state, [ForceDiscardOrDefeatStep(victim_key="victim_id")])
    result = process_stack(state)

    assert result.input_request is None
    assert len(state.execution_stack) == 0
