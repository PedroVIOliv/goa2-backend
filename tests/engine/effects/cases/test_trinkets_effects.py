from __future__ import annotations

import pytest

import goa2.scripts.trinkets_effects  # noqa: F401
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, Turret
from goa2.domain.types import BoardEntityID
from goa2.engine.effects import CardEffectRegistry

from ..builders import EffectScenarioBuilder, hero_card, skill_card
from ..runner import run_card

TURRET_ID = BoardEntityID("trinkets_turret")


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


@pytest.mark.effect_contract
def test_salvage_parts_is_registered() -> None:
    assert CardEffectRegistry.get("salvage_parts") is not None


@pytest.mark.effect_flow
def test_salvage_parts_places_unique_turret_as_obstacle() -> None:
    turret_hex = Hex(q=1, r=0, s=-1)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "salvage_parts"),
        )
        .with_actor("hero_trinkets")
        .build()
    )

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_HEX)
    assert turret_hex in _option_set(run)

    run.choose(turret_hex).finish()

    turret = state.misc_entities[TURRET_ID]
    assert isinstance(turret, Turret)
    assert turret.owner_id == "hero_trinkets"
    assert state.entity_locations[TURRET_ID] == turret_hex
    assert state.board.get_tile(turret_hex).occupant_id == TURRET_ID
    assert TURRET_ID not in state.get_units_and_tokens()
    assert any(e.event_type == GameEventType.BOARD_ENTITY_PLACED for e in run.events)


@pytest.mark.effect_flow
def test_salvage_parts_remove_turret_and_move() -> None:
    turret_hex = Hex(q=1, r=0, s=-1)
    move_hex = Hex(q=3, r=0, s=-3)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "salvage_parts"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    state.register_entity(Turret(id=TURRET_ID, name="Turret", owner_id="hero_trinkets"))
    state.place_entity(TURRET_ID, turret_hex)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_HEX)
    assert move_hex in _option_set(run)

    run.choose(move_hex).finish()

    assert TURRET_ID not in state.entity_locations
    assert state.board.get_tile(turret_hex).occupant_id is None
    assert state.entity_locations["hero_trinkets"] == move_hex
    assert any(e.event_type == GameEventType.BOARD_ENTITY_REMOVED for e in run.events)


@pytest.mark.effect_flow
def test_salvage_parts_remove_turret_and_retrieve_card() -> None:
    turret_hex = Hex(q=1, r=0, s=-1)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "salvage_parts"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    hero = state.get_hero("hero_trinkets")
    assert hero is not None
    discarded = skill_card("discarded_tool", "Discarded Tool")
    discarded.state = CardState.DISCARD
    hero.discard_pile.append(discarded)
    state.register_entity(Turret(id=TURRET_ID, name="Turret", owner_id="hero_trinkets"))
    state.place_entity(TURRET_ID, turret_hex)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(3)
    run.expect_input(InputRequestType.SELECT_CARD).choose("discarded_tool")
    run.finish()

    assert TURRET_ID not in state.entity_locations
    assert discarded in hero.hand
    assert discarded not in hero.discard_pile
    assert any(e.event_type == GameEventType.BOARD_ENTITY_REMOVED for e in run.events)
    assert any(e.event_type == GameEventType.CARD_RETRIEVED for e in run.events)


@pytest.mark.effect_flow
@pytest.mark.parametrize("choice", [2, 3])
def test_salvage_parts_remove_branches_abort_without_turret(choice: int) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "salvage_parts"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    hero = state.get_hero("hero_trinkets")
    assert hero is not None
    discarded = skill_card("discarded_tool", "Discarded Tool")
    discarded.state = CardState.DISCARD
    hero.discard_pile.append(discarded)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(choice)
    run.finish()

    assert state.entity_locations["hero_trinkets"] == Hex(q=0, r=0, s=0)
    assert discarded in hero.discard_pile
    assert discarded not in hero.hand
    assert not any(e.event_type == GameEventType.BOARD_ENTITY_REMOVED for e in run.events)
