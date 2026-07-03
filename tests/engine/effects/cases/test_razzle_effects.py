"""Razzle multi-piece card effects."""

import pytest

import goa2.scripts.razzle_effects  # noqa: F401 - register effects
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState
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


def _hex_disk(radius: int) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if -radius <= -q - r <= radius
    ]


def _pos(state, entity_id: str) -> tuple[int, int, int] | None:
    loc = state.entity_locations.get(entity_id)
    return None if loc is None else (loc.q, loc.r, loc.s)


def _option_ids(run) -> set[str]:
    assert run.latest_request is not None
    return {option.id for option in run.latest_request.options}


def _number_options(run) -> set[int]:
    assert run.latest_request is not None
    return {int(option.id) for option in run.latest_request.options}


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


@pytest.mark.effect_flow
def test_alleyoop_can_swap_with_non_acting_razzle_piece_then_move_it():
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "alleyoop"),
        )
        .blue_minion("blue_minion", at=(3, 0, -3))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (1, 0, -1)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 1))
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert piece_id("hero_razzle", 2) in _option_ids(run)
    run.choose(piece_id("hero_razzle", 2))
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert piece_id("hero_razzle", 1) not in _option_ids(run)
    run.choose(piece_id("hero_razzle", 2))
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": -1, "r": 0, "s": 1})
    run.finish()

    assert _pos(state, piece_id("hero_razzle", 1)) == (1, 0, -1)
    assert _pos(state, piece_id("hero_razzle", 2)) == (-1, 0, 1)


@pytest.mark.effect_flow
def test_magic_trick_push_stopped_by_edge_moves_razzle_actual_distance():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(-1, 0, 1), (0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "magic_trick"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.expect_input(InputRequestType.SELECT_NUMBER)
    assert 2 in _number_options(run)
    run.choose(2).finish()

    assert _pos(state, "blue_minion") == (2, 0, -2)
    assert _pos(state, piece_id("hero_razzle", 1)) == (-1, 0, 1)


@pytest.mark.effect_flow
def test_magic_trick_excludes_push_distance_when_razzle_cannot_mirror_actual_move():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "magic_trick"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.expect_input(InputRequestType.SELECT_NUMBER)
    assert _number_options(run) == {0}
    run.choose(0).finish()

    assert _pos(state, "blue_minion") == (1, 0, -1)
    assert _pos(state, piece_id("hero_razzle", 1)) == (0, 0, 0)


@pytest.mark.effect_flow
def test_high_wire_moves_another_piece_after_primary_movement():
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "high_wire"),
        )
        .blue_minion("blue_minion", at=(4, 0, -4))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (2, 0, -2)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 1))
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 0, "r": 1, "s": -1})
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 2))
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 2, "r": 1, "s": -3})
    run.finish()

    assert _pos(state, piece_id("hero_razzle", 1)) == (0, 1, -1)
    assert _pos(state, piece_id("hero_razzle", 2)) == (2, 1, -3)


@pytest.mark.effect_flow
def test_spectacle_repeats_by_another_piece_on_a_different_minion():
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "spectacle"),
        )
        .blue_minion("minion_a", at=(1, 0, -1))
        .blue_minion("minion_b", at=(0, 2, -2))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (0, 1, -1)])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 1))
    run.expect_input(InputRequestType.SELECT_UNIT).choose("minion_a")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 2))
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert "minion_a" not in _option_ids(run)
    assert "minion_b" in _option_ids(run)
    run.choose("minion_b").finish()

    assert _pos(state, piece_id("hero_razzle", 1)) == (1, 0, -1)
    assert _pos(state, "minion_a") == (0, 0, 0)
    assert _pos(state, piece_id("hero_razzle", 2)) == (0, 2, -2)
    assert _pos(state, "minion_b") == (0, 1, -1)
    assert state.acting_piece_id == piece_id("hero_razzle", 2)


@pytest.mark.effect_flow
def test_into_thin_air_can_remove_all_pieces_without_defeat():
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "into_thin_air"),
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
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 1))
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 2))
    run.finish()

    assert state.get_piece_ids("hero_razzle") == []
    assert "hero_razzle" not in state.heroes_defeated_this_round


@pytest.mark.effect_flow
def test_ransack_retrieves_once_for_each_other_piece_in_radius():
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "ransack"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (1, -1, 0), (3, 0, -3)])
    razzle = state.get_hero("hero_razzle")
    card_a = hero_card("Razzle", "alleyoop")
    card_b = hero_card("Razzle", "tightrope")
    card_a.state = CardState.DISCARD
    card_b.state = CardState.DISCARD
    razzle.discard_pile.extend([card_a, card_b])

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 1))
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.expect_input(InputRequestType.SELECT_CARD).choose(card_a.id)
    run.expect_input(InputRequestType.SELECT_CARD).choose(card_b.id)
    run.finish()

    assert [card.id for card in razzle.hand][-2:] == [card_a.id, card_b.id]


@pytest.mark.effect_flow
def test_stunt_doubles_with_twin_strike_repeats_full_primary_by_another_piece_once():
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_razzle",
            at=(0, 0, 0),
            current_card=hero_card("Razzle", "stunt_doubles"),
        )
        .blue_minion("minion_a", at=(1, 0, -1))
        .blue_minion("minion_b", at=(0, 2, -2))
        .with_actor("hero_razzle")
        .build()
    )
    _piece_setup(state, [(0, 0, 0), (0, 1, -1)])
    razzle = state.get_hero("hero_razzle")
    razzle.level = 8
    razzle.ultimate_card = hero_card("Razzle", "twin_strike")
    razzle.ultimate_card.state = CardState.PASSIVE

    run = run_card(state, "hero_razzle")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 1))
    run.expect_input(InputRequestType.SELECT_UNIT).choose("minion_a")
    run.expect_input(InputRequestType.SELECT_HEX).skip()
    run.expect_input(InputRequestType.SELECT_UNIT).choose(piece_id("hero_razzle", 2))
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert "minion_a" not in _option_ids(run)
    assert "minion_b" in _option_ids(run)
    run.choose("minion_b")
    run.expect_input(InputRequestType.SELECT_HEX).skip()
    run.finish()

    assert state.acting_piece_id == piece_id("hero_razzle", 2)
