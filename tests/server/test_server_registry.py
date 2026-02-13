"""Unit tests for GameRegistry."""

import pytest

from goa2.engine.setup import GameSetup
from goa2.engine.session import GameSession
from goa2.server.registry import GameRegistry, ManagedGame
from goa2.server.errors import GameNotFoundError

MAP_PATH = "src/goa2/data/maps/forgotten_island.json"


@pytest.fixture
def registry():
    return GameRegistry()


@pytest.fixture
def session():
    state = GameSetup.create_game(MAP_PATH, ["Arien"], ["Wasp"])
    return GameSession(state)


def test_create_game(registry, session):
    game = registry.create_game(session, ["hero_arien", "hero_wasp"])
    assert isinstance(game, ManagedGame)
    assert len(game.game_id) == 12
    assert len(game.player_tokens) == 2
    assert len(game.hero_to_token) == 2
    assert game.spectator_token


def test_get_existing_game(registry, session):
    game = registry.create_game(session, ["hero_arien", "hero_wasp"])
    fetched = registry.get(game.game_id)
    assert fetched is game


def test_get_missing_game_raises(registry):
    with pytest.raises(GameNotFoundError):
        registry.get("nonexistent")


def test_resolve_player_token(registry, session):
    game = registry.create_game(session, ["hero_arien", "hero_wasp"])
    token = game.hero_to_token["hero_arien"]
    result = registry.resolve_token(token)
    assert result is not None
    game_id, hero_id, is_spectator = result
    assert game_id == game.game_id
    assert hero_id == "hero_arien"
    assert is_spectator is False


def test_resolve_spectator_token(registry, session):
    game = registry.create_game(session, ["hero_arien", "hero_wasp"])
    result = registry.resolve_token(game.spectator_token)
    assert result is not None
    game_id, hero_id, is_spectator = result
    assert game_id == game.game_id
    assert hero_id == ""
    assert is_spectator is True


def test_resolve_unknown_token(registry):
    assert registry.resolve_token("bogus") is None


def test_remove_game(registry, session):
    game = registry.create_game(session, ["hero_arien", "hero_wasp"])
    registry.remove(game.game_id)
    with pytest.raises(GameNotFoundError):
        registry.get(game.game_id)


def test_registry_len(registry, session):
    assert len(registry) == 0
    registry.create_game(session, ["hero_arien"])
    assert len(registry) == 1
