import pytest

from goa2.domain.events import GameEventType
from goa2.domain.models import TeamColor
from goa2.domain.models.effect import DurationType, EffectType

from ..assertions import assert_effect_active, assert_event_emitted, assert_valid_options
from ..builders import EffectScenarioBuilder, movement_card
from ..runner import run_card


@pytest.fixture
def static_barrier_state():
    return (
        EffectScenarioBuilder()
        .small_arena()
        .hero("hero_wasp", team=TeamColor.RED, at=(0, 0, 0), current_card="static_barrier")
        .enemy_hero("enemy_inside", at=(1, 0, -1), current_card=movement_card(value=3))
        .enemy_hero("enemy_outside", at=(4, 0, -4), current_card=movement_card(value=3))
        .with_actor("hero_wasp")
        .with_unresolved_heroes(["enemy_inside"])
        .build()
    )


@pytest.mark.effect_contract
def test_static_barrier_contract_creates_active_enemy_hero_barrier(static_barrier_state):
    run = run_card(static_barrier_state, "hero_wasp", finalize_turn=True)

    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("CHOOSE_ACTION")

    assert_effect_active(
        static_barrier_state,
        EffectType.STATIC_BARRIER,
        source_id="hero_wasp",
    )
    effect = next(
        effect
        for effect in static_barrier_state.active_effects
        if effect.effect_type == EffectType.STATIC_BARRIER
    )
    assert effect.barrier_radius == 2
    assert effect.barrier_origin_id == "hero_wasp"
    assert effect.duration == DurationType.THIS_TURN
    assert_event_emitted(
        run.events,
        GameEventType.EFFECT_CREATED,
        actor_id="hero_wasp",
    )


@pytest.mark.effect_contract
def test_static_barrier_contract_blocks_enemy_movement_across_radius(static_barrier_state):
    run = run_card(static_barrier_state, "hero_wasp", finalize_turn=True)

    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("CHOOSE_ACTION").choose("MOVEMENT")
    run.expect_input("SELECT_HEX")

    assert_valid_options(
        run.latest_request,
        contains=[(0, 1, -1), (1, 1, -2)],
        excludes=[
            (3, 0, -3),
            (4, 0, -4),
            (3, 1, -4),
        ],
    )
