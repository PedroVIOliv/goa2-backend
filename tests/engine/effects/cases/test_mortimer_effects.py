from __future__ import annotations

import pytest

from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import Token, TokenType
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.steps import EndPhaseCleanupStep

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
