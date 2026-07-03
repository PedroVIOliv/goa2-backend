"""Razzle validation cards: stunt_doubles, phantom_strike, crowd_control."""

import pytest

import goa2.scripts.razzle_effects  # noqa: F401 - register effects
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.combat import AttackSequenceStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _piece_setup(state, positions: list[tuple[int, int, int]]):
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    for i, (q, r, s) in enumerate(positions):
        state.place_entity(piece_id("hero_razzle", i + 1), Hex(q=q, r=r, s=s))


@pytest.mark.effect_flow
def test_stunt_doubles_attacks_then_spawns_up_to_supply():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1), (1, -1, 0), (-1, 1, 0)])
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "stunt_doubles"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.expect_input(InputRequestType.SELECT_HEX)
    first = run.latest_request.options[0].metadata["hex"]
    run.choose(first)
    run.expect_input(InputRequestType.SELECT_HEX).skip().finish()

    assert len(state.get_piece_ids("hero_razzle")) == 2


@pytest.mark.effect_flow
def test_phantom_strike_offers_removal_only_with_multiple_pieces():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "phantom_strike"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (0, 1, -1)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 1))
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 2))
    run.finish()

    assert state.get_piece_ids("hero_razzle") == [piece_id("hero_razzle", 1)]


@pytest.mark.effect_flow
def test_crowd_control_skill_removes_all_other_pieces():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "crowd_control"),
        )
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (1, 0, -1), (0, 1, -1)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 2))
    run.finish()

    assert state.get_piece_ids("hero_razzle") == [piece_id("hero_razzle", 2)]


@pytest.mark.effect_flow
def test_crowd_control_defense_bonus_counts_other_pieces_in_radius():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (1, 0, -1), (0, 1, -1)])
    razzle = state.get_hero("hero_razzle")
    crowd_control = hero_card("Razzle", "crowd_control")
    razzle.hand.append(crowd_control)

    push_steps(state, [AttackSequenceStep(damage=4, range_val=1)])
    result = process_stack(state)
    assert result.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}

    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.SELECT_CARD_OR_PASS
    state.execution_stack[-1].pending_input = {"selection": crowd_control.id}

    result = process_stack(state)
    events = [e for e in result.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert events and events[-1].metadata["outcome"] == "BLOCKED"
