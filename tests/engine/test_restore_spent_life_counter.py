from __future__ import annotations

from goa2.domain.events import GameEventType
from goa2.domain.models import TeamColor
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.setup import GameSetup
from goa2.engine.steps import RestoreSpentLifeCounterStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _state():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0)])
        .red_hero("hero_actor", at=(0, 0, 0))
        .with_actor("hero_actor")
        .build()
    )
    team = state.teams[TeamColor.RED]
    team.starting_life_counters = 5
    return state, team


def test_restore_spent_life_counter_restores_one_and_emits_event() -> None:
    state, team = _state()
    team.life_counters = 3
    push_steps(state, [RestoreSpentLifeCounterStep(hero_id="hero_actor")])

    result = process_stack(state)

    assert team.life_counters == 4
    event = next(
        event for event in result.events if event.event_type == GameEventType.LIFE_COUNTER_CHANGED
    )
    assert event.actor_id == "hero_actor"
    assert event.metadata == {
        "team": TeamColor.RED.value,
        "change": 1,
        "remaining": 4,
        "reason": "life_counter_restored",
    }


def test_restore_spent_life_counter_never_exceeds_starting_supply() -> None:
    state, team = _state()
    team.life_counters = 5
    push_steps(state, [RestoreSpentLifeCounterStep(hero_id="hero_actor")])

    result = process_stack(state)

    assert team.life_counters == 5
    assert result.events == []


def test_starting_life_counter_supply_survives_game_setup_and_json_round_trip() -> None:
    state = GameSetup.create_game(
        "src/goa2/data/maps/forgotten_island.json",
        ["Gydion"],
        ["Wasp"],
        game_type="QUICK",
    )
    assert state.teams[TeamColor.RED].starting_life_counters == 3
    state.teams[TeamColor.RED].life_counters = 1

    restored = GameState.model_validate_json(state.model_dump_json())

    assert restored.teams[TeamColor.RED].life_counters == 1
    assert restored.teams[TeamColor.RED].starting_life_counters == 3
