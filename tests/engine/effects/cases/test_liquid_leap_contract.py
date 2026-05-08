import pytest

from goa2.domain.events import GameEventType
from goa2.domain.models import TeamColor

from ..assertions import (
    assert_event_emitted,
    assert_position,
    assert_valid_options,
)
from ..builders import EffectScenarioBuilder
from ..runner import run_card


@pytest.fixture
def liquid_leap_state():
    return (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (1, -1, 0),
                (0, 1, -1),
                (2, -1, -1),
            ]
        )
        .spawn_point((1, -1, 0), team=TeamColor.RED)
        .hero("hero_arien", team=TeamColor.RED, at=(0, 0, 0), current_card="liquid_leap")
        .with_actor("hero_arien")
        .build()
    )


@pytest.mark.effect_contract
def test_liquid_leap_contract_selects_only_non_spawn_safe_hexes(liquid_leap_state):
    run = run_card(liquid_leap_state, "hero_arien")

    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("SELECT_HEX")

    assert_valid_options(
        run.latest_request,
        contains=[(2, 0, -2), (0, 1, -1)],
        excludes=[
            (1, 0, -1),  # adjacent to empty spawn
            (1, -1, 0),  # spawn point
            (2, -1, -1),  # adjacent to empty spawn
            (0, 0, 0),  # occupied by Arien
        ],
    )


@pytest.mark.effect_contract
def test_liquid_leap_contract_places_arien_and_emits_event(liquid_leap_state):
    run = run_card(liquid_leap_state, "hero_arien")

    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("SELECT_HEX").choose({"q": 2, "r": 0, "s": -2})
    run.finish()

    assert_position(liquid_leap_state, "hero_arien", (2, 0, -2))
    assert_event_emitted(
        run.events,
        GameEventType.UNIT_PLACED,
        actor_id="hero_arien",
    )
