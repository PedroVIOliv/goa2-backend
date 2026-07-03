"""Defeating any piece defeats the hero: rewards once, all pieces removed."""

from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.combat import DefeatUnitStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _state() -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    state.place_entity(piece_id("hero_razzle", 3), Hex(q=0, r=1, s=-1))
    return state


def test_defeating_one_piece_removes_all_and_rewards_once():
    state = _state()
    knight = state.get_hero("hero_knight")
    razzle = state.get_hero("hero_razzle")
    gold_before = knight.gold
    life_before = state.teams[razzle.team].life_counters

    push_steps(
        state, [DefeatUnitStep(victim_id=piece_id("hero_razzle", 2), killer_id="hero_knight")]
    )
    process_stack(state)

    for i in (1, 2, 3):
        assert piece_id("hero_razzle", i) not in state.entity_locations
    assert not state.has_board_presence("hero_razzle")
    # Level-1 kill reward = 1 gold, exactly once
    assert knight.gold == gold_before + 1
    # Exactly one life counter penalty
    assert state.teams[razzle.team].life_counters == life_before - 1
    assert "hero_razzle" in state.heroes_defeated_this_round
