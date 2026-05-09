from __future__ import annotations

import pytest

from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, Token, TokenType
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.setup import GameSetup

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _option_set(run) -> set:
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if hasattr(option, "metadata") and option.metadata and "raw" in option.metadata:
            options.add(option.metadata.get("raw"))
        elif hasattr(option, "id"):
            options.add(option.id)
        else:
            options.add(option)
    return options


def _add_pyro_pool(state) -> None:
    state.token_pool[TokenType.PYRO] = []
    token = Token(
        id="pyro_1",
        name="Pyro",
        token_type=TokenType.PYRO,
        persists_end_of_round=True,
    )
    state.register_entity(token)
    state.token_pool[TokenType.PYRO].append(token)


@pytest.mark.effect_contract
def test_widget_easy_effects_are_registered() -> None:
    for effect_id in [
        "dragon_bond",
        "take_off",
        "all_aboard",
        "safe_landing",
        "diversionary_strike",
        "fight_as_one",
        "diversionary_attack",
        "diversionary_assault",
        "airborne_attack",
        "airborne_assault",
        "nibble",
        "gnaw",
        "fiery_breath",
        "flaming_breath",
        "scorching_breath",
    ]:
        assert CardEffectRegistry.get(effect_id) is not None


@pytest.mark.effect_contract
def test_setup_creates_persistent_pyro_token() -> None:
    state = EffectScenarioBuilder().line_board().red_hero("hero_widget", at=(0, 0, 0)).build()
    GameSetup._initialize_token_pool(state)

    assert len(state.token_pool[TokenType.PYRO]) == 1
    assert state.token_pool[TokenType.PYRO][0].persists_end_of_round


@pytest.mark.effect_flow
def test_dragon_bond_places_pyro_in_radius() -> None:
    pyro_hex = Hex(q=1, r=0, s=-1)
    far_hex = Hex(q=3, r=0, s=-3)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_widget",
            at=(0, 0, 0),
            current_card=hero_card("Widget", "dragon_bond"),
        )
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_HEX)
    assert pyro_hex in _option_set(run)
    assert far_hex not in _option_set(run)

    run.choose(pyro_hex).finish()

    assert state.entity_locations["pyro_1"] == pyro_hex
    assert state.token_pool[TokenType.PYRO][0].persists_end_of_round
    assert any(e.event_type == GameEventType.TOKEN_PLACED for e in run.events)


@pytest.mark.effect_flow
def test_dragon_bond_move_branch_aborts_if_pyro_is_not_in_play() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_widget",
            at=(0, 0, 0),
            current_card=hero_card("Widget", "dragon_bond"),
        )
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).finish()

    assert "pyro_1" not in state.entity_locations
    assert state.entity_locations["hero_widget"] == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_dragon_bond_moves_pyro_then_widget_when_chosen() -> None:
    widget_start = Hex(q=0, r=0, s=0)
    pyro_start = Hex(q=2, r=0, s=-2)
    pyro_dest = Hex(q=3, r=0, s=-3)
    widget_dest = Hex(q=1, r=0, s=-1)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_widget",
            at=widget_start,
            current_card=hero_card("Widget", "dragon_bond"),
        )
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)
    state.place_entity("pyro_1", pyro_start)

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).expect_input(InputRequestType.SELECT_NUMBER)
    assert state.execution_context["dragon_bond_pyro"] == "pyro_1"

    run.choose(2).expect_input(InputRequestType.SELECT_HEX)
    assert pyro_dest in _option_set(run)

    run.choose(pyro_dest).expect_input(InputRequestType.SELECT_HEX)
    assert widget_dest in _option_set(run)

    run.choose(widget_dest).finish()

    assert state.entity_locations["pyro_1"] == pyro_dest
    assert state.entity_locations["hero_widget"] == widget_dest
    assert sum(e.event_type == GameEventType.TOKEN_MOVED for e in run.events) == 1
    assert sum(e.event_type == GameEventType.UNIT_MOVED for e in run.events) == 1


@pytest.mark.effect_flow
def test_take_off_swaps_pyro_with_widget() -> None:
    widget_start = Hex(q=0, r=0, s=0)
    pyro_start = Hex(q=2, r=0, s=-2)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_widget",
            at=widget_start,
            current_card=hero_card("Widget", "take_off"),
        )
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)
    state.place_entity("pyro_1", pyro_start)

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert state.execution_context["pyro_swap_id"] == "pyro_1"

    assert _option_set(run) == {"hero_widget"}

    run.choose("hero_widget").finish()

    assert state.entity_locations["hero_widget"] == pyro_start
    assert state.entity_locations["pyro_1"] == widget_start
    assert any(e.event_type == GameEventType.UNITS_SWAPPED for e in run.events)


@pytest.mark.effect_flow
def test_safe_landing_may_move_pyro_then_swap_with_friendly_hero() -> None:
    pyro_start = Hex(q=2, r=0, s=-2)
    pyro_move_dest = Hex(q=2, r=1, s=-3)
    ally_start = Hex(q=1, r=0, s=-1)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (2, 1, -3)])
        .red_hero(
            "hero_widget",
            at=(0, 0, 0),
            current_card=hero_card("Widget", "safe_landing"),
        )
        .red_hero("friendly_widget_ally", at=ally_start)
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)
    state.place_entity("pyro_1", pyro_start)

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("pyro_1").expect_input(InputRequestType.SELECT_HEX)
    assert pyro_move_dest in _option_set(run)

    run.choose(pyro_move_dest).expect_input(InputRequestType.SELECT_UNIT)
    assert state.execution_context["pyro_swap_id"] == "pyro_1"
    assert _option_set(run) == {"hero_widget", "friendly_widget_ally"}

    run.choose("friendly_widget_ally").finish()

    assert state.entity_locations["pyro_1"] == ally_start
    assert state.entity_locations["friendly_widget_ally"] == pyro_move_dest
    assert any(e.event_type == GameEventType.TOKEN_MOVED for e in run.events)
    assert any(e.event_type == GameEventType.UNITS_SWAPPED for e in run.events)


@pytest.mark.effect_flow
def test_diversionary_strike_attacks_then_moves_pyro_up_to_two() -> None:
    pyro_start = Hex(q=1, r=1, s=-2)
    pyro_dest = Hex(q=3, r=1, s=-4)
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (1, 1, -2),
                (2, 1, -3),
                (3, 1, -4),
            ]
        )
        .red_hero(
            "hero_widget",
            at=(0, 0, 0),
            current_card=hero_card("Widget", "diversionary_strike"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)
    state.place_entity("pyro_1", pyro_start)

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    assert _option_set(run) == {"pyro_1"}

    run.choose("pyro_1").expect_input(InputRequestType.SELECT_HEX)
    assert pyro_dest in _option_set(run)

    run.choose(pyro_dest).finish()

    assert state.entity_locations["pyro_1"] == pyro_dest
    combat_events = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat_events
    assert combat_events[-1].metadata["attack_value"] == 5
    assert any(e.event_type == GameEventType.TOKEN_MOVED for e in run.events)


@pytest.mark.effect_flow
def test_fight_as_one_replays_resolved_skill_against_different_unit() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (0, 1, -1), (1, 0, -1), (1, 1, -2)])
        .red_hero(
            "hero_widget",
            at=(0, 0, 0),
            current_card=hero_card("Widget", "fight_as_one"),
        )
        .blue_hero("blue_initial_target", at=(1, 0, -1))
        .blue_hero("blue_replay_target", at=(1, 1, -2))
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)
    state.place_entity("pyro_1", Hex(q=0, r=1, s=-1))

    widget = state.get_hero("hero_widget")
    assert widget is not None
    played_skill = hero_card("Widget", "fiery_breath")
    played_skill.state = CardState.RESOLVED
    widget.played_cards.append(played_skill)

    initial_target = state.get_hero("blue_initial_target")
    assert initial_target is not None
    initial_target.hand.append(hero_card("Widget", "dragon_bond"))

    replay_target = state.get_hero("blue_replay_target")
    assert replay_target is not None
    replay_target.hand.append(hero_card("Widget", "all_aboard"))

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_initial_target").expect_input(InputRequestType.SELECT_CARD_OR_PASS)
    run.choose("dragon_bond").expect_input(InputRequestType.SELECT_CARD)
    assert _option_set(run) == {"fiery_breath"}

    run.choose("fiery_breath").expect_input(InputRequestType.SELECT_UNIT)
    assert state.execution_context["pyro_breath_id"] == "pyro_1"
    assert _option_set(run) == {"blue_replay_target"}

    run.choose("blue_replay_target").expect_input(InputRequestType.SELECT_CARD)
    run.choose("all_aboard").finish()

    assert state.execution_context["fight_as_one_initial_target"] == "blue_initial_target"
    assert state.entity_locations["blue_initial_target"] == Hex(q=1, r=0, s=-1)
    assert len(replay_target.hand) == 0
    assert replay_target.discard_pile[0].id == "all_aboard"


@pytest.mark.effect_flow
def test_airborne_assault_can_swap_before_and_after_attack() -> None:
    widget_start = Hex(q=0, r=0, s=0)
    pyro_start = Hex(q=2, r=0, s=-2)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_widget",
            at=widget_start,
            current_card=hero_card("Widget", "airborne_assault"),
        )
        .red_hero("friendly_widget_ally", at=(3, 0, -3))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)
    state.place_entity("pyro_1", pyro_start)

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("pyro_1").expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_widget"}

    run.choose("hero_widget").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("pyro_1").expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_widget"}

    run.choose("hero_widget").finish()

    assert state.entity_locations["hero_widget"] == widget_start
    assert state.entity_locations["pyro_1"] == pyro_start
    assert sum(e.event_type == GameEventType.UNITS_SWAPPED for e in run.events) == 2
    combat_events = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat_events[-1].metadata["attack_value"] == 4


@pytest.mark.effect_flow
def test_nibble_removes_enemy_minion_adjacent_to_pyro_then_removes_pyro() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (4, 0, -4)])
        .red_hero(
            "hero_widget",
            at=(0, 0, 0),
            current_card=hero_card("Widget", "nibble"),
        )
        .blue_minion("blue_minion", at=(3, 0, -3))
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)
    state.place_entity("pyro_1", Hex(q=4, r=0, s=-4))

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert state.execution_context["pyro_skill_id"] == "pyro_1"
    assert _option_set(run) == {"blue_minion"}

    run.choose("blue_minion").finish()

    assert "blue_minion" not in state.entity_locations
    assert "pyro_1" not in state.entity_locations
    assert any(e.event_type == GameEventType.UNIT_REMOVED for e in run.events)
    assert any(e.event_type == GameEventType.TOKEN_REMOVED for e in run.events)


@pytest.mark.effect_flow
def test_fiery_breath_forces_straight_line_enemy_hero_to_discard() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (2, 1, -3)])
        .red_hero(
            "hero_widget",
            at=(0, 0, 0),
            current_card=hero_card("Widget", "fiery_breath"),
        )
        .blue_hero("blue_target", at=(2, 0, -2))
        .blue_hero("blue_offline", at=(2, 1, -3))
        .with_actor("hero_widget")
        .build()
    )
    _add_pyro_pool(state)
    state.place_entity("pyro_1", Hex(q=1, r=0, s=-1))
    target = state.get_hero("blue_target")
    assert target is not None
    target.hand.append(hero_card("Widget", "all_aboard"))

    run = run_card(state, "hero_widget")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert state.execution_context["pyro_breath_id"] == "pyro_1"
    assert _option_set(run) == {"blue_target"}

    run.choose("blue_target").expect_input(InputRequestType.SELECT_CARD)
    run.choose("all_aboard").finish()

    assert len(target.hand) == 0
    assert len(target.discard_pile) == 1
    assert target.discard_pile[0].id == "all_aboard"
