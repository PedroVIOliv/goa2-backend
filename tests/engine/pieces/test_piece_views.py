"""Player-scoped views expose hero pieces with owner metadata."""

from goa2.domain.hex import Hex
from goa2.domain.views import build_view
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from tests.engine.effects.builders import EffectScenarioBuilder


def test_view_contains_hero_pieces_section():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))

    view = build_view(state, for_hero_id=None)
    pieces = view["hero_pieces"]

    assert pieces[piece_id("hero_razzle", 1)]["owner_hero_id"] == "hero_razzle"
    assert pieces[piece_id("hero_razzle", 1)]["position"] == {"q": 0, "r": 0, "s": 0}
    assert pieces[piece_id("hero_razzle", 2)]["position"] is None
    assert pieces[piece_id("hero_razzle", 1)]["team"] == "RED"
    assert piece_id("hero_razzle", 1) in view["board"]["entity_locations"]
