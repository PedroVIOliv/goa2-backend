"""HeroPiece model, registration, and GameState lookup resolution."""

from goa2.domain.hex import Hex
from goa2.domain.models import Hero, HeroPiece, TeamColor
from goa2.domain.state import GameState
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from tests.engine.effects.builders import EffectScenarioBuilder


def _multi_piece_state() -> GameState:
    """Blue Knight vs a 4-supply Razzle with two pieces on board."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (0, 1, -1), (1, 1, -2)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    # Multi-piece heroes are never board entities themselves.
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    return state


def test_piece_id_format():
    assert piece_id("hero_razzle", 1) == "hero_razzle_piece_1"


def test_create_hero_pieces_registers_supply_in_misc_entities():
    state = _multi_piece_state()
    for i in range(1, 5):
        entity = state.misc_entities.get(piece_id("hero_razzle", i))
        assert isinstance(entity, HeroPiece)
        assert entity.owner_hero_id == "hero_razzle"
        assert entity.team == TeamColor.RED


def test_get_unit_resolves_piece():
    state = _multi_piece_state()
    unit = state.get_unit(piece_id("hero_razzle", 2))
    assert isinstance(unit, HeroPiece)


def test_get_hero_resolves_piece_to_owner():
    state = _multi_piece_state()
    hero = state.get_hero(piece_id("hero_razzle", 2))
    assert isinstance(hero, Hero)
    assert hero.id == "hero_razzle"


def test_get_hero_still_finds_normal_heroes():
    state = _multi_piece_state()
    assert state.get_hero("hero_knight").id == "hero_knight"
    assert state.get_hero("nonexistent") is None


def test_hero_piece_persistence_round_trip():
    state = _multi_piece_state()
    raw = state.model_dump_json()
    restored = GameState.model_validate_json(raw)
    entity = restored.misc_entities.get("hero_razzle_piece_1")
    assert isinstance(entity, HeroPiece)
    assert entity.owner_hero_id == "hero_razzle"
    assert restored.entity_locations.get("hero_razzle_piece_2") == Hex(q=1, r=0, s=-1)
