from __future__ import annotations

import pytest

from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import Token, TokenType
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import EndPhaseCleanupStep
from goa2.scripts.mortimer_effects import _dead_choice_steps

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


def _option_texts(run) -> list[str]:
    assert run.latest_request is not None
    return [option.text for option in run.latest_request.options]


def _add_zombie_pool(state) -> None:
    state.token_pool[TokenType.ZOMBIE] = []
    for i in range(4):
        token = Token(
            id=f"zombie_{i + 1}",
            name="Zombie",
            token_type=TokenType.ZOMBIE,
            persists_end_of_round=True,
        )
        state.register_entity(token)
        state.token_pool[TokenType.ZOMBIE].append(token)


@pytest.mark.effect_contract
def test_master_of_puppets_effect_is_registered_as_passive_modifier() -> None:
    effect = CardEffectRegistry.get("master_of_puppets")

    assert effect is not None
    assert effect.get_passive_config() is None


@pytest.mark.effect_flow
def test_awaken_places_zombies_adjacent_or_on_spawn_points() -> None:
    adjacent_hex = Hex(q=1, r=0, s=-1)
    other_adjacent_hex = Hex(q=0, r=1, s=-1)
    spawn_hex = Hex(q=0, r=2, s=-2)
    invalid_hex = Hex(q=2, r=0, s=-2)
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (0, 1, -1),
                (0, 2, -2),
                (2, 0, -2),
            ]
        )
        .spawn_point(spawn_hex)
        .red_hero("hero_mortimer", at=(0, 0, 0), current_card=hero_card("Mortimer", "awaken"))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    assert [option.id for option in run.latest_request.options] == ["SKILL", "HOLD"]

    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    assert _option_set(run) == {adjacent_hex, other_adjacent_hex, spawn_hex}

    run.choose(adjacent_hex).expect_input(InputRequestType.SELECT_HEX)
    assert _option_set(run) == {other_adjacent_hex, spawn_hex}
    assert invalid_hex not in _option_set(run)

    run.choose(other_adjacent_hex)
    run.expect_input(InputRequestType.SELECT_HEX)
    assert _option_set(run) == {spawn_hex}

    run.choose(spawn_hex)
    run.finish()

    zombie_locations = {
        location
        for token in state.token_pool[TokenType.ZOMBIE]
        if (location := state.entity_locations.get(token.id)) is not None
    }
    assert zombie_locations == {adjacent_hex, other_adjacent_hex, spawn_hex}
    assert all(token.persists_end_of_round for token in state.token_pool[TokenType.ZOMBIE])
    assert sum(e.event_type == GameEventType.TOKEN_PLACED for e in run.events) == 3


@pytest.mark.effect_contract
def test_awaken_zombies_persist_through_end_phase_cleanup() -> None:
    zombie_hex = Hex(q=1, r=0, s=-1)
    state = EffectScenarioBuilder().line_board().red_hero("hero_mortimer", at=(0, 0, 0)).build()
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_hex)

    result = EndPhaseCleanupStep().resolve(state, {})

    assert state.entity_locations["zombie_1"] == zombie_hex
    assert not any(e.event_type == GameEventType.TOKEN_REMOVED for e in result.events)


@pytest.mark.effect_flow
def test_knife_of_the_living_dead_removes_zombies_for_attack_bonus() -> None:
    target_hex = Hex(q=1, r=0, s=-1)
    zombie_a = Hex(q=2, r=0, s=-2)
    zombie_b = Hex(q=1, r=1, s=-2)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (1, 1, -2)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "knife_of_the_living_dead"),
        )
        .blue_minion("blue_minion", at=target_hex)
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_a)
    state.place_entity("zombie_2", zombie_b)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"blue_minion"}

    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)
    assert "up to 3" in run.latest_request.prompt
    assert _option_texts(run) == [
        "Move a Zombie token in radius 1 space",
        "Remove a Zombie token adjacent to the target for +1 Attack",
    ]

    run.choose(2).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    assert _option_set(run) == {"zombie_1", "zombie_2"}

    run.choose("zombie_1").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    assert _option_set(run) == {"zombie_2"}

    run.choose("zombie_2").expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert "zombie_1" not in state.entity_locations
    assert "zombie_2" not in state.entity_locations
    combat_events = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat_events
    assert combat_events[-1].metadata["attack_value"] == 6
    assert any(e.event_type == GameEventType.TOKEN_REMOVED for e in run.events)


@pytest.mark.effect_flow
def test_knife_of_the_living_dead_can_move_zombie_before_attack() -> None:
    zombie_start = Hex(q=1, r=1, s=-2)
    zombie_dest = Hex(q=2, r=1, s=-3)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (1, 1, -2), (2, 1, -3)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "knife_of_the_living_dead"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").expect_input(InputRequestType.SELECT_HEX)
    assert zombie_dest in _option_set(run)

    run.choose(zombie_dest).expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert state.entity_locations["zombie_1"] == zombie_dest
    combat_events = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat_events[-1].metadata["attack_value"] == 4


@pytest.mark.effect_flow
def test_stage_dive_can_move_zombie_token_in_range() -> None:
    zombie_start = Hex(q=1, r=0, s=-1)
    zombie_dest = Hex(q=1, r=1, s=-2)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (1, 1, -2), (2, 0, -2)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "stage_dive"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    assert _option_texts(run) == [
        "Move a Zombie token in range 1 space",
        "Swap with a Zombie token in range",
    ]
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    assert _option_set(run) == {"zombie_1"}

    run.choose("zombie_1").expect_input(InputRequestType.SELECT_HEX)
    assert zombie_dest in _option_set(run)

    run.choose(zombie_dest).finish()

    assert state.entity_locations["zombie_1"] == zombie_dest
    assert any(e.event_type == GameEventType.TOKEN_MOVED for e in run.events)


@pytest.mark.effect_flow
def test_stage_dive_can_swap_with_zombie_token_in_range() -> None:
    mortimer_start = Hex(q=0, r=0, s=0)
    zombie_start = Hex(q=2, r=0, s=-2)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_mortimer",
            at=mortimer_start,
            current_card=hero_card("Mortimer", "stage_dive"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    assert _option_texts(run) == [
        "Move a Zombie token in range 1 space",
        "Swap with a Zombie token in range",
    ]
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").finish()

    assert state.entity_locations["hero_mortimer"] == zombie_start
    assert state.entity_locations["zombie_1"] == mortimer_start
    assert any(e.event_type == GameEventType.UNITS_SWAPPED for e in run.events)


@pytest.mark.effect_flow
def test_corpse_slam_can_move_zombie_and_push_from_zombie() -> None:
    zombie_start = Hex(q=1, r=0, s=-1)
    zombie_dest = Hex(q=1, r=1, s=-2)
    enemy_start = Hex(q=2, r=1, s=-3)
    enemy_dest = Hex(q=3, r=1, s=-4)
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
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "corpse_slam"),
        )
        .blue_minion("blue_minion", at=enemy_start)
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    assert _option_texts(run) == [
        "Move a Zombie token in range up to 1 space; it may push adjacent",
        "Move 1 space",
    ]
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").expect_input(InputRequestType.SELECT_HEX)
    run.choose(zombie_dest).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    assert _option_set(run) == {"blue_minion"}

    run.choose("blue_minion").finish()

    assert state.entity_locations["zombie_1"] == zombie_dest
    assert state.entity_locations["blue_minion"] == enemy_dest
    assert any(e.event_type == GameEventType.UNIT_PUSHED for e in run.events)


@pytest.mark.effect_flow
def test_corpse_slam_can_move_mortimer_one_space() -> None:
    destination = Hex(q=1, r=0, s=-1)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "corpse_slam"),
        )
        .with_actor("hero_mortimer")
        .build()
    )

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    assert _option_texts(run) == [
        "Move a Zombie token in range up to 1 space; it may push adjacent",
        "Move 1 space",
    ]
    run.choose(2).expect_input(InputRequestType.SELECT_HEX)
    assert destination in _option_set(run)

    run.choose(destination).finish()

    assert state.entity_locations["hero_mortimer"] == destination
    assert any(e.event_type == GameEventType.UNIT_MOVED for e in run.events)


@pytest.mark.effect_flow
def test_crowd_drift_can_choose_twice_then_stops() -> None:
    mortimer_start = Hex(q=0, r=0, s=0)
    zombie_start = Hex(q=2, r=0, s=-2)
    zombie_dest = Hex(q=1, r=0, s=-1)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (2, 1, -3)])
        .red_hero(
            "hero_mortimer",
            at=mortimer_start,
            current_card=hero_card("Mortimer", "crowd_drift"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    assert "up to 2" in run.latest_request.prompt

    assert _option_texts(run) == [
        "Move a Zombie token in range 1 space",
        "Swap with a Zombie token in range",
    ]
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").expect_input(InputRequestType.SELECT_NUMBER)

    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").expect_input(InputRequestType.SELECT_HEX)
    run.choose(zombie_dest).finish()

    assert state.entity_locations["hero_mortimer"] == zombie_start
    assert state.entity_locations["zombie_1"] == zombie_dest
    assert sum(e.event_type == GameEventType.UNITS_SWAPPED for e in run.events) == 1
    assert sum(e.event_type == GameEventType.TOKEN_MOVED for e in run.events) == 1


@pytest.mark.effect_flow
def test_crowd_surf_prompts_for_three_choices_without_ultimate() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "crowd_surf"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)

    assert "up to 3" in run.latest_request.prompt


@pytest.mark.effect_flow
def test_crowd_surf_prompts_for_five_choices_with_master_of_puppets() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "crowd_surf"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    mortimer = state.get_hero("hero_mortimer")
    assert mortimer is not None
    mortimer.level = 8
    mortimer.ultimate_card = hero_card("Mortimer", "master_of_puppets")
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)

    assert "up to 5" in run.latest_request.prompt


@pytest.mark.effect_flow
def test_gathering_horde_replaces_enemy_minion_adjacent_to_two_zombies() -> None:
    minion_hex = Hex(q=2, r=0, s=-2)
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (1, 1, -2),
                (2, 0, -2),
                (2, -1, -1),
                (3, 0, -3),
            ]
        )
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "gathering_horde"),
        )
        .blue_minion("blue_minion", at=minion_hex)
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=1, r=0, s=-1))
    state.place_entity("zombie_2", Hex(q=2, r=-1, s=-1))

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    assert "up to 2" in run.latest_request.prompt
    assert _option_texts(run) == [
        "Move a Zombie token in range 1 space",
        "Replace an enemy minion adjacent to two or more Zombie tokens",
    ]

    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"blue_minion"}

    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert "blue_minion" not in state.entity_locations
    assert state.entity_locations["zombie_3"] == minion_hex
    assert any(e.event_type == GameEventType.UNIT_REMOVED for e in run.events)
    assert any(e.event_type == GameEventType.TOKEN_PLACED for e in run.events)


@pytest.mark.effect_flow
def test_gathering_horde_replacement_requires_two_adjacent_zombies() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "gathering_horde"),
        )
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert state.entity_locations["blue_minion"] == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_army_of_darkness_prompts_for_five_choices_with_master_of_puppets() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "army_of_darkness"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    mortimer = state.get_hero("hero_mortimer")
    assert mortimer is not None
    mortimer.level = 8
    mortimer.ultimate_card = hero_card("Mortimer", "master_of_puppets")
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)

    assert "up to 5" in run.latest_request.prompt


@pytest.mark.effect_flow
def test_robbing_zombies_moves_zombie_and_gains_coin() -> None:
    zombie_start = Hex(q=1, r=0, s=-1)
    zombie_dest = Hex(q=1, r=1, s=-2)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (1, 1, -2), (2, 0, -2)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "robbing_zombies"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)
    mortimer = state.get_hero("hero_mortimer")
    assert mortimer is not None
    assert mortimer.gold == 0

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    assert "up to 2" in run.latest_request.prompt
    assert _option_texts(run) == [
        "Move a Zombie token in range up to 1 space and gain 1 coin",
        "Move 1 space",
    ]

    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").expect_input(InputRequestType.SELECT_HEX)
    run.choose(zombie_dest).expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert state.entity_locations["zombie_1"] == zombie_dest
    assert mortimer.gold == 1
    assert any(e.event_type == GameEventType.GOLD_GAINED for e in run.events)


@pytest.mark.effect_flow
def test_robbing_zombies_can_choose_current_zombie_hex_and_gain_coin() -> None:
    zombie_start = Hex(q=1, r=0, s=-1)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (1, 1, -2)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "robbing_zombies"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)
    mortimer = state.get_hero("hero_mortimer")
    assert mortimer is not None

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").expect_input(InputRequestType.SELECT_HEX)
    assert zombie_start in _option_set(run)

    run.choose(zombie_start).expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert state.entity_locations["zombie_1"] == zombie_start
    assert mortimer.gold == 1
    assert any(e.event_type == GameEventType.GOLD_GAINED for e in run.events)


@pytest.mark.effect_flow
def test_morbid_mosh_can_move_zombie_and_push_from_zombie() -> None:
    zombie_start = Hex(q=1, r=0, s=-1)
    zombie_dest = Hex(q=1, r=1, s=-2)
    enemy_start = Hex(q=2, r=1, s=-3)
    enemy_dest = Hex(q=3, r=1, s=-4)
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
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "morbid_mosh"),
        )
        .blue_minion("blue_minion", at=enemy_start)
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    assert "up to 2" in run.latest_request.prompt

    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").expect_input(InputRequestType.SELECT_HEX)
    run.choose(zombie_dest).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert state.entity_locations["zombie_1"] == zombie_dest
    assert state.entity_locations["blue_minion"] == enemy_dest
    assert any(e.event_type == GameEventType.UNIT_PUSHED for e in run.events)


@pytest.mark.effect_flow
def test_stalking_scalpers_prompts_for_five_choices_with_master_of_puppets() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "stalking_scalpers"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    mortimer = state.get_hero("hero_mortimer")
    assert mortimer is not None
    mortimer.level = 8
    mortimer.ultimate_card = hero_card("Mortimer", "master_of_puppets")
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)

    assert "up to 5" in run.latest_request.prompt


@pytest.mark.effect_flow
def test_macabre_mayhem_prompts_for_three_choices_without_ultimate() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "macabre_mayhem"),
        )
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)

    assert "up to 3" in run.latest_request.prompt


@pytest.mark.effect_flow
def test_braaaaaaaaains_can_move_zombie_before_attack() -> None:
    zombie_start = Hex(q=2, r=0, s=-2)
    zombie_dest = Hex(q=2, r=1, s=-3)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (2, 1, -3)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "braaaaaaaaains"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"blue_minion"}

    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)
    assert "up to 3" in run.latest_request.prompt
    assert _option_texts(run) == [
        "Move a Zombie token in radius 1 space",
        "Retrieve a discarded card if an enemy hero in radius is adjacent to a Zombie token",
    ]

    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").expect_input(InputRequestType.SELECT_HEX)
    assert zombie_dest in _option_set(run)

    run.choose(zombie_dest).expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert state.entity_locations["zombie_1"] == zombie_dest
    combat_events = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat_events, "expected the attack to resolve after the choice phase"
    assert combat_events[-1].metadata["attack_value"] == 7


@pytest.mark.effect_flow
def test_braaaaaaaaains_retrieves_discarded_card_when_zombie_pins_enemy_hero() -> None:
    target_hex = Hex(q=1, r=0, s=-1)
    zombie_hex = Hex(q=2, r=0, s=-2)
    enemy_hero_hex = Hex(q=3, r=0, s=-3)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), target_hex, zombie_hex, enemy_hero_hex])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "braaaaaaaaains"),
        )
        .blue_hero("hero_enemy", at=enemy_hero_hex)
        .blue_minion("blue_minion", at=target_hex)
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_hex)

    mortimer = state.get_hero("hero_mortimer")
    assert mortimer is not None
    discarded = hero_card("Mortimer", "stage_dive")
    mortimer.discard_pile = [discarded]

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)

    run.choose(2).expect_input(InputRequestType.SELECT_CARD)
    assert discarded.id in _option_set(run)

    run.choose(discarded.id).expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert discarded in mortimer.hand
    assert discarded not in mortimer.discard_pile
    assert any(e.event_type == GameEventType.CARD_RETRIEVED for e in run.events)


@pytest.mark.effect_flow
def test_braaaaaaaaains_skips_retrieve_when_no_enemy_hero_pinned() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "braaaaaaaaains"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=2, r=0, s=-2))

    mortimer = state.get_hero("hero_mortimer")
    assert mortimer is not None
    discarded = hero_card("Mortimer", "stage_dive")
    mortimer.discard_pile = [discarded]

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)

    # Choose retrieve, but with no eligible enemy hero pinned by a zombie
    # the retrieve branch is gated off, so we land on the next choice
    # prompt without ever seeing a SELECT_CARD request.
    run.choose(2).expect_input(InputRequestType.SELECT_NUMBER)
    run.skip().finish()

    assert discarded in mortimer.discard_pile
    assert discarded not in mortimer.hand
    assert not any(e.event_type == GameEventType.CARD_RETRIEVED for e in run.events)


@pytest.mark.effect_flow
def test_braaains_prompts_for_two_choices() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "braaains"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)

    assert "up to 2" in run.latest_request.prompt


@pytest.mark.effect_flow
def test_braaaaaaaaains_prompts_for_five_choices_with_master_of_puppets() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "braaaaaaaaains"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    mortimer = state.get_hero("hero_mortimer")
    assert mortimer is not None
    mortimer.level = 8
    mortimer.ultimate_card = hero_card("Mortimer", "master_of_puppets")
    _add_zombie_pool(state)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)

    assert "up to 5" in run.latest_request.prompt


@pytest.mark.effect_flow
def test_crawling_dead_attacks_then_moves_zombie() -> None:
    zombie_start = Hex(q=2, r=0, s=-2)
    zombie_dest = Hex(q=2, r=1, s=-3)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (2, 1, -3)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "crawling_dead"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", zombie_start)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)

    # T1 "Choose one" — mandatory single iteration, no SKIP option.
    assert "up to" not in run.latest_request.prompt
    assert _option_texts(run) == [
        "Move a Zombie token in radius 1 space",
        "An enemy hero in radius adjacent to a Zombie token discards a card",
    ]

    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_1").expect_input(InputRequestType.SELECT_HEX)
    run.choose(zombie_dest).finish()

    assert state.entity_locations["zombie_1"] == zombie_dest
    combat_events = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat_events, "expected the attack to resolve before the choice phase"
    assert combat_events[-1].metadata["attack_value"] == 6


@pytest.mark.effect_flow
def test_crawling_dead_forces_hero_discard_when_zombie_pins_enemy_hero() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "crawling_dead"),
        )
        .blue_hero("hero_enemy", at=(3, 0, -3))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=2, r=0, s=-2))

    enemy = state.get_hero("hero_enemy")
    assert enemy is not None
    victim_card = hero_card("Mortimer", "stage_dive")
    enemy.hand = [victim_card]

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)

    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_enemy"}

    run.choose("hero_enemy").expect_input(InputRequestType.SELECT_CARD)
    run.choose(victim_card.id).finish()

    assert victim_card not in enemy.hand
    assert victim_card in enemy.discard_pile


@pytest.mark.effect_flow
def test_walking_dead_enforces_each_hero_only_once() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (3, 0, -3),
                (1, 1, -2),
                (1, 2, -3),
            ]
        )
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "walking_dead"),
        )
        .blue_hero("hero_a", at=(3, 0, -3))
        .blue_hero("hero_b", at=(1, 2, -3))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    state.place_entity("zombie_1", Hex(q=2, r=0, s=-2))
    state.place_entity("zombie_2", Hex(q=1, r=1, s=-2))

    hero_a = state.get_hero("hero_a")
    hero_b = state.get_hero("hero_b")
    assert hero_a is not None and hero_b is not None
    card_a = hero_card("Mortimer", "stage_dive")
    card_b = hero_card("Mortimer", "corpse_slam")
    hero_a.hand = [card_a]
    hero_b.hand = [card_b]

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)
    assert "up to 2" in run.latest_request.prompt

    # First choice: discard from hero_a — both heroes are eligible.
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_a", "hero_b"}

    run.choose("hero_a").expect_input(InputRequestType.SELECT_CARD)
    run.choose(card_a.id).expect_input(InputRequestType.SELECT_NUMBER)

    # Second choice: only hero_b remains selectable — once-per-hero excludes hero_a.
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_b"}

    run.choose("hero_b").expect_input(InputRequestType.SELECT_CARD)
    run.choose(card_b.id).finish()

    assert card_a in hero_a.discard_pile
    assert card_b in hero_b.discard_pile


@pytest.mark.effect_flow
def test_racing_dead_prompts_for_five_choices_with_master_of_puppets() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "racing_dead"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    mortimer = state.get_hero("hero_mortimer")
    assert mortimer is not None
    mortimer.level = 8
    mortimer.ultimate_card = hero_card("Mortimer", "master_of_puppets")
    _add_zombie_pool(state)

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)

    assert "up to 5" in run.latest_request.prompt


@pytest.mark.effect_flow
def test_racing_dead_excludes_all_prior_picks_at_three_deep() -> None:
    """Iteration 2 must drop *both* iter-0 and iter-1 picks, not just the most recent."""
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (3, 0, -3),
                (1, 1, -2),
                (3, -1, -2),
            ]
        )
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "racing_dead"),
        )
        .blue_hero("hero_a", at=(3, 0, -3))
        .blue_hero("hero_b", at=(1, 1, -2))
        .blue_hero("hero_c", at=(3, -1, -2))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    # Single zombie pinning all three enemy heroes (each adjacent to it).
    state.place_entity("zombie_1", Hex(q=2, r=0, s=-2))

    hero_a = state.get_hero("hero_a")
    hero_b = state.get_hero("hero_b")
    hero_c = state.get_hero("hero_c")
    assert hero_a is not None and hero_b is not None and hero_c is not None
    card_a = hero_card("Mortimer", "stage_dive")
    card_b = hero_card("Mortimer", "corpse_slam")
    card_c = hero_card("Mortimer", "awaken")
    hero_a.hand = [card_a]
    hero_b.hand = [card_b]
    hero_c.hand = [card_c]

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)

    # Iter 0: pick hero_a — pool has all three.
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_a", "hero_b", "hero_c"}
    run.choose("hero_a").expect_input(InputRequestType.SELECT_CARD)
    run.choose(card_a.id).expect_input(InputRequestType.SELECT_NUMBER)

    # Iter 1: hero_a must be excluded.
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_b", "hero_c"}
    run.choose("hero_b").expect_input(InputRequestType.SELECT_CARD)
    run.choose(card_b.id).expect_input(InputRequestType.SELECT_NUMBER)

    # Iter 2: both hero_a AND hero_b must be excluded — only hero_c remains.
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_c"}
    run.choose("hero_c").expect_input(InputRequestType.SELECT_CARD)
    run.choose(card_c.id).finish()

    assert card_a in hero_a.discard_pile
    assert card_b in hero_b.discard_pile
    assert card_c in hero_c.discard_pile


@pytest.mark.effect_flow
def test_walking_dead_move_zombie_does_not_consume_a_hero_slot() -> None:
    """If iter 0 picks the move-zombie option, iter 1's discard pool is still full."""
    move_dest = Hex(q=-2, r=0, s=2)
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (3, 0, -3),
                (1, 1, -2),
                (1, 2, -3),
                (-1, 0, 1),
                (-2, 0, 2),
            ]
        )
        .red_hero(
            "hero_mortimer",
            at=(0, 0, 0),
            current_card=hero_card("Mortimer", "walking_dead"),
        )
        .blue_hero("hero_a", at=(3, 0, -3))
        .blue_hero("hero_b", at=(1, 2, -3))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    # Two zombies pin the heroes, plus a third zombie we'll move (harmlessly).
    state.place_entity("zombie_1", Hex(q=2, r=0, s=-2))  # pins hero_a
    state.place_entity("zombie_2", Hex(q=1, r=1, s=-2))  # pins hero_b
    state.place_entity("zombie_3", Hex(q=-1, r=0, s=1))  # gets moved away

    hero_a = state.get_hero("hero_a")
    hero_b = state.get_hero("hero_b")
    assert hero_a is not None and hero_b is not None
    card_a = hero_card("Mortimer", "stage_dive")
    card_b = hero_card("Mortimer", "corpse_slam")
    hero_a.hand = [card_a]
    hero_b.hand = [card_b]

    run = run_card(state, "hero_mortimer")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)

    # Iter 0: pick "move zombie" (option 1) — no hero is consumed.
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("zombie_3").expect_input(InputRequestType.SELECT_HEX)
    run.choose(move_dest).expect_input(InputRequestType.SELECT_NUMBER)

    # Iter 1: discard pool must still include BOTH heroes — the move-zombie
    # branch must not have left a stale hero key in the exclusion list.
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_a", "hero_b"}

    run.choose("hero_a").expect_input(InputRequestType.SELECT_CARD)
    run.choose(card_a.id).finish()

    assert state.entity_locations["zombie_3"] == move_dest
    assert card_a in hero_a.discard_pile
    assert card_b in hero_b.hand  # untouched


@pytest.mark.effect_contract
def test_dead_choice_excludes_attack_target_when_target_is_a_hero() -> None:
    """The attack target ("dead_target") is always excluded from the discard pool,
    so the card's "another enemy hero" wording holds even when the target is a hero.

    Driven via the raw-stack pattern: we push only the post-attack choice steps
    and pre-populate ``dead_target`` in context, sidestepping the reaction
    window that a real hero-vs-hero attack would trigger.
    """
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (3, 0, -3),
            ]
        )
        .red_hero("hero_mortimer", at=(0, 0, 0))
        .blue_hero("hero_target", at=(1, 0, -1))
        .blue_hero("hero_other", at=(3, 0, -3))
        .with_actor("hero_mortimer")
        .build()
    )
    _add_zombie_pool(state)
    # Zombie pins BOTH heroes (each adjacent to it).
    state.place_entity("zombie_1", Hex(q=2, r=0, s=-2))

    hero_target = state.get_hero("hero_target")
    hero_other = state.get_hero("hero_other")
    assert hero_target is not None and hero_other is not None
    hero_target.hand = [hero_card("Mortimer", "stage_dive")]
    hero_other.hand = [hero_card("Mortimer", "corpse_slam")]

    # Simulate "attack just resolved on hero_target" by seeding the context.
    state.execution_context["dead_target"] = "hero_target"
    push_steps(
        state,
        _dead_choice_steps(
            "test_dead_target_excl",
            radius=4,
            prompt="Choose one",
            is_mandatory=True,
        ),
    )

    # First request: SELECT_NUMBER for the choice. Pick option 2 (discard).
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.SELECT_NUMBER
    state.execution_stack[-1].pending_input = {"selection": 2}

    # Next request: SELECT_UNIT for the discard target. hero_target must be
    # excluded ("another enemy hero"); only hero_other should remain.
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.SELECT_UNIT
    options = {opt.id for opt in result.input_request.options}
    assert options == {"hero_other"}
    assert "hero_target" not in options
