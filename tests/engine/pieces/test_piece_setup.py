"""Game setup places pieces (not the hero) for multi-piece heroes."""

from goa2.data.heroes.knight import create_knight
from goa2.data.heroes.registry import HeroRegistry
from goa2.engine.setup import GameSetup

MAP_PATH = "src/goa2/data/maps/forgotten_island.json"


def _ensure_knight_registered() -> None:
    # `knight.py` is a dummy/test-only hero, deliberately excluded from the
    # package-wide `data/heroes/__init__.py` registration list (see
    # `scripts/check_card_items.py:SKIP_MODULES`). Register it explicitly so
    # setup can resolve "Knight" as a normal (non-multi-piece) hero.
    if HeroRegistry.get("Knight") is None:
        HeroRegistry.register(create_knight())


def test_create_game_places_piece_not_hero():
    _ensure_knight_registered()

    state = GameSetup.create_game(
        MAP_PATH,
        red_heroes=["Razzle", "Wasp"],
        blue_heroes=["Knight", "Tali"],
    )

    assert "hero_razzle" not in state.entity_locations
    assert "hero_razzle_piece_1" in state.entity_locations
    # Supply pieces registered but off-board
    for i in (2, 3, 4):
        assert f"hero_razzle_piece_{i}" in state.misc_entities
        assert f"hero_razzle_piece_{i}" not in state.entity_locations
    # Normal heroes unaffected
    assert "hero_knight" in state.entity_locations
    assert state.has_board_presence("hero_razzle")
