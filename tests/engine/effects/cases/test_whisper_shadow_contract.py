import pytest

from goa2.domain.events import GameEventType
from goa2.domain.models import TeamColor
from goa2.domain.models.spawn import SpawnType

from ..assertions import assert_event_emitted, assert_position, assert_valid_options
from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


@pytest.fixture
def whisper_shadow_state():
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (3, 0, -3),
                (4, 0, -4),
                (0, 1, -1),
                (1, 1, -2),
                (2, 1, -3),
                (3, 1, -4),
                (0, 2, -2),
                (1, 2, -3),
                (2, 2, -4),
            ]
        )
        .spawn_point((2, 0, -2), team=TeamColor.RED, spawn_type=SpawnType.MINION)
        .spawn_point((3, 0, -3), team=TeamColor.RED, spawn_type=SpawnType.MINION)
        .spawn_point((4, 0, -4), team=TeamColor.RED, spawn_type=SpawnType.MINION)
        .red_hero(
            "hero_whisper",
            at=(0, 0, 0),
            current_card=hero_card("Whisper", "shadow_step"),
        )
        .blue_minion("enemy_on_spawn", at=(3, 0, -3))
        .blue_minion("enemy_elsewhere", at=(0, 2, -2))
        .with_actor("hero_whisper")
        .build()
    )
    state.active_zone_id = "z1"
    return state


@pytest.mark.effect_contract
def test_shadow_step_contract_selects_only_empty_spawn_points_in_range(whisper_shadow_state):
    run = run_card(whisper_shadow_state, "hero_whisper")

    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("SELECT_HEX")

    assert_valid_options(
        run.latest_request,
        contains=[(2, 0, -2)],
        excludes=[
            (1, 0, -1),  # empty, but not a spawn point
            (3, 0, -3),  # spawn point occupied by enemy_on_spawn
            (4, 0, -4),  # spawn point outside Shadow Step range
            (0, 0, 0),  # occupied by Whisper
        ],
    )


@pytest.mark.effect_contract
def test_shadow_step_contract_places_whisper_and_emits_event(whisper_shadow_state):
    run = run_card(whisper_shadow_state, "hero_whisper")

    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("SELECT_HEX").choose({"q": 2, "r": 0, "s": -2})
    run.finish()

    assert_position(whisper_shadow_state, "hero_whisper", (2, 0, -2))
    assert_event_emitted(
        run.events,
        GameEventType.UNIT_PLACED,
        actor_id="hero_whisper",
    )


@pytest.mark.effect_contract
def test_creeping_shadow_contract_can_choose_spawn_or_adjacent_spawn_hex(
    whisper_shadow_state,
):
    whisper_shadow_state.get_hero("hero_whisper").current_turn_card = hero_card(
        "Whisper", "creeping_shadow"
    )
    run = run_card(whisper_shadow_state, "hero_whisper")

    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("SELECT_HEX")

    assert_valid_options(
        run.latest_request,
        contains=[
            (2, 0, -2),  # empty spawn point
            (1, 0, -1),  # adjacent to an empty spawn point
            (2, 1, -3),  # adjacent to an empty spawn point
            (4, 0, -4),  # in range for Creeping Shadow
        ],
        excludes=[
            (3, 0, -3),  # occupied spawn point
            (0, 0, 0),  # occupied by Whisper
        ],
    )


@pytest.fixture
def whisper_mixed_spawn_state():
    """Whisper with a MINION spawn point and a HERO spawn point both empty,
    in range, and in the active battle zone."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)])
        .spawn_point((1, 0, -1), team=TeamColor.RED, spawn_type=SpawnType.HERO)
        .spawn_point((2, 0, -2), team=TeamColor.RED, spawn_type=SpawnType.MINION)
        .red_hero(
            "hero_whisper",
            at=(0, 0, 0),
            current_card=hero_card("Whisper", "shadow_step"),
        )
        .with_actor("hero_whisper")
        .build()
    )
    state.active_zone_id = "z1"
    return state


@pytest.mark.effect_contract
def test_shadow_step_excludes_hero_spawn_points(whisper_mixed_spawn_state):
    """ "Place yourself into an empty minion spawn point" — hero spawn points
    must NOT qualify, only minion spawn points."""
    run = run_card(whisper_mixed_spawn_state, "hero_whisper")

    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("SELECT_HEX")

    assert_valid_options(
        run.latest_request,
        contains=[(2, 0, -2)],  # minion spawn point
        excludes=[(1, 0, -1)],  # hero spawn point — not a minion spawn point
    )


@pytest.mark.effect_contract
def test_creeping_shadow_excludes_isolated_hero_spawn_point():
    """Creeping Shadow targets minion spawn points (or hexes adjacent to one).
    A hero spawn point with no minion spawn point nearby must not qualify."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)])
        .spawn_point((2, 0, -2), team=TeamColor.RED, spawn_type=SpawnType.MINION)
        .spawn_point((4, 0, -4), team=TeamColor.RED, spawn_type=SpawnType.HERO)
        .red_hero(
            "hero_whisper",
            at=(0, 0, 0),
            current_card=hero_card("Whisper", "creeping_shadow"),
        )
        .with_actor("hero_whisper")
        .build()
    )
    state.active_zone_id = "z1"

    run = run_card(state, "hero_whisper")
    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("SELECT_HEX")

    assert_valid_options(
        run.latest_request,
        contains=[
            (2, 0, -2),  # minion spawn point itself
            (3, 0, -3),  # adjacent to the minion spawn point
        ],
        excludes=[
            (4, 0, -4),  # hero spawn point, not adjacent to any minion spawn point
        ],
    )


@pytest.mark.effect_contract
def test_crimson_trail_counts_only_minion_spawn_points():
    """Crimson Trail's pre-move distance counts empty MINION spawn points only;
    hero spawn points in radius must not grant movement."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(4)] + [(0, 1, -1)])
        .spawn_point((1, 0, -1), team=TeamColor.RED, spawn_type=SpawnType.HERO)
        .spawn_point((2, 0, -2), team=TeamColor.RED, spawn_type=SpawnType.HERO)
        .red_hero(
            "hero_whisper",
            at=(0, 0, 0),
            current_card=hero_card("Whisper", "crimson_trail"),
        )
        .blue_minion("blue_minion", at=(0, 1, -1))
        .with_actor("hero_whisper")
        .build()
    )
    state.active_zone_id = "z1"

    run = run_card(state, "hero_whisper")
    # Only hero spawn points in radius → no pre-move → straight to the attack
    # target selection (no SELECT_HEX move prompt).
    run.expect_input("CHOOSE_ACTION").choose("ATTACK")
    run.expect_input("SELECT_UNIT")
