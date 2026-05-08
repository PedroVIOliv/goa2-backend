from __future__ import annotations

import pytest

from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import Token, TokenType
from goa2.engine.steps import EndPhaseCleanupStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _option_set(run) -> set:
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if hasattr(option, "metadata"):
            options.add(option.metadata.get("raw"))
        else:
            options.add(option)
    return options


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
