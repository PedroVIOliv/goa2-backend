"""Fix 4 guards: stat markers stay piece-local for action/defense stats,
aggregate once at owner level for initiative, and clean up on defeat."""

from goa2.domain.hex import Hex
from goa2.domain.models import StatType, TeamColor
from goa2.domain.models.marker import MarkerType
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.stats import get_computed_stat
from goa2.engine.steps.combat import DefeatUnitStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _state() -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(4, 0, -4))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=2, r=0, s=-2))
    return state


def test_place_marker_on_piece_stays_on_piece():
    state = _state()
    marker = state.place_marker(
        MarkerType.POISON, piece_id("hero_razzle", 2), value=-2, source_id="hero_knight"
    )
    assert marker.target_id == piece_id("hero_razzle", 2)


def test_poison_on_piece_is_piece_local_for_attack_and_defense():
    state = _state()
    state.place_marker(
        MarkerType.POISON, piece_id("hero_razzle", 2), value=-2, source_id="hero_knight"
    )

    assert get_computed_stat(state, piece_id("hero_razzle", 2), StatType.ATTACK, 4) == 2
    assert get_computed_stat(state, piece_id("hero_razzle", 2), StatType.DEFENSE, 4) == 2
    # The unpoisoned piece does not inherit the penalty.
    assert get_computed_stat(state, piece_id("hero_razzle", 1), StatType.ATTACK, 4) == 4
    assert get_computed_stat(state, piece_id("hero_razzle", 1), StatType.DEFENSE, 4) == 4


def test_poison_on_piece_counts_once_for_owner_initiative():
    state = _state()
    state.place_marker(
        MarkerType.POISON, piece_id("hero_razzle", 2), value=-2, source_id="hero_knight"
    )

    assert get_computed_stat(state, "hero_razzle", StatType.INITIATIVE, 5) == 3
    # Initiative is owner-level regardless of which piece you ask about.
    assert get_computed_stat(state, piece_id("hero_razzle", 1), StatType.INITIATIVE, 5) == 3


def test_defeat_returns_piece_marker_and_pays_bounty():
    state = _state()
    state.place_marker(
        MarkerType.POISON, piece_id("hero_razzle", 1), value=-2, source_id="hero_knight"
    )
    state.place_marker(
        MarkerType.BOUNTY, piece_id("hero_razzle", 2), value=1, source_id="hero_knight"
    )
    red_team = state.teams[TeamColor.RED]
    counters_before = red_team.life_counters

    push_steps(
        state,
        [DefeatUnitStep(victim_id=piece_id("hero_razzle", 1), killer_id="hero_knight")],
    )
    process_stack(state)

    # Both piece-attached markers returned to supply on hero defeat.
    assert state.markers[MarkerType.POISON].target_id is None
    assert state.markers[MarkerType.BOUNTY].target_id is None
    # Bounty adds one extra life counter to the level-1 death penalty.
    assert red_team.life_counters == counters_before - 2
