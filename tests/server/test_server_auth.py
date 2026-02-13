"""Unit tests for auth dependency."""

import pytest
from unittest.mock import MagicMock

from fastapi import HTTPException

from goa2.server.auth import get_current_player, PlayerContext
from goa2.server.registry import GameRegistry, ManagedGame
from goa2.engine.setup import GameSetup
from goa2.engine.session import GameSession

MAP_PATH = "src/goa2/data/maps/forgotten_island.json"


@pytest.fixture
def registry():
    return GameRegistry()


@pytest.fixture
def game(registry):
    state = GameSetup.create_game(MAP_PATH, ["Arien"], ["Wasp"])
    session = GameSession(state)
    return registry.create_game(session, ["hero_arien", "hero_wasp"])


def _make_request(token: str, path_params: dict | None = None):
    """Create a mock request with auth header and path params."""
    req = MagicMock()
    req.headers = {"Authorization": f"Bearer {token}"} if token else {}
    req.path_params = path_params or {}
    return req


def test_valid_player_token(registry, game):
    token = game.hero_to_token["hero_arien"]
    req = _make_request(token, {"game_id": game.game_id})
    ctx = get_current_player(req, registry)
    assert isinstance(ctx, PlayerContext)
    assert ctx.hero_id == "hero_arien"
    assert ctx.is_spectator is False
    assert ctx.game_id == game.game_id


def test_valid_spectator_token(registry, game):
    req = _make_request(game.spectator_token, {"game_id": game.game_id})
    ctx = get_current_player(req, registry)
    assert ctx.is_spectator is True
    assert ctx.hero_id == ""


def test_missing_auth_header(registry):
    req = MagicMock()
    req.headers = {}
    with pytest.raises(HTTPException) as exc_info:
        get_current_player(req, registry)
    assert exc_info.value.status_code == 401


def test_invalid_token(registry):
    req = _make_request("badtoken")
    with pytest.raises(HTTPException) as exc_info:
        get_current_player(req, registry)
    assert exc_info.value.status_code == 401


def test_wrong_game_id(registry, game):
    token = game.hero_to_token["hero_arien"]
    req = _make_request(token, {"game_id": "wrong_game_id"})
    with pytest.raises(HTTPException) as exc_info:
        get_current_player(req, registry)
    assert exc_info.value.status_code == 403


def test_no_game_id_in_path(registry, game):
    """Token is valid even without game_id in path (e.g. listing endpoints)."""
    token = game.hero_to_token["hero_wasp"]
    req = _make_request(token)
    ctx = get_current_player(req, registry)
    assert ctx.hero_id == "hero_wasp"
