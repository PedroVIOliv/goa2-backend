"""Dodger's Death Trap must see Razzle pieces as targetable enemy heroes."""

from goa2.domain.hex import Hex
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.stats import CardStats
from goa2.scripts.dodger_effects import DeathTrapEffect
from tests.engine.effects.builders import EffectScenarioBuilder, hero_card, skill_card


def _state() -> GameState:
    """Dodger at (4,0,-4); Razzle pieces at (0,0,0) and (2,0,-2).

    Empty spawn point at (3,0,-3), adjacent to piece_2 only. Radius 4 keeps
    piece_1 in range but not spawn-adjacent, so it must be excluded.
    """
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(6)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_dodger", at=(4, 0, -4))
        .spawn_point((3, 0, -3))
        .with_actor("hero_dodger")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    razzle.hand = [skill_card("razzle_hand_card")]
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=2, r=0, s=-2))

    state.active_zone_id = "z1"
    state.board.tiles[Hex(q=3, r=0, s=-3)].zone_id = "z1"
    return state


def test_death_trap_targets_spawn_adjacent_piece_only():
    state = _state()
    dodger = state.get_hero("hero_dodger")
    card = hero_card("Dodger", "death_trap")

    steps = DeathTrapEffect().build_steps(
        state, dodger, card, CardStats(primary_value=0, range=1, radius=4)
    )
    assert steps, "Death Trap found no valid targets — pieces are invisible to it"

    push_steps(state, steps)
    result = process_stack(state)
    assert result.input_request is not None

    option_ids = {o.id for o in result.input_request.options}
    # piece_2 is spawn-adjacent and in radius → targetable
    assert piece_id("hero_razzle", 2) in option_ids
    # piece_1 is in radius but NOT spawn-adjacent → excluded
    assert piece_id("hero_razzle", 1) not in option_ids
    assert "hero_razzle" not in option_ids
