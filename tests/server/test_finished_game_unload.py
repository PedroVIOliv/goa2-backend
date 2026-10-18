"""Finished games leave memory once idle and load back from disk on demand."""

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from goa2.domain.models import GamePhase, TeamColor
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.server.app import create_app
from goa2.server.errors import GameNotFoundError
from goa2.server.registry import GameRegistry

MAP_PATH = "src/goa2/data/maps/forgotten_island.json"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _finish(registry: GameRegistry, game_id: str) -> None:
    state = registry.get(game_id).session.state
    state.phase = GamePhase.GAME_OVER
    state.winner = TeamColor.RED
    state.execution_stack.clear()
    registry.save_game(game_id)


@pytest.fixture
def registry(tmp_path):
    return GameRegistry(save_dir=str(tmp_path))


def _new_game(registry: GameRegistry):
    state = GameSetup.create_game(MAP_PATH, ["Arien"], ["Wasp"])
    return registry.create_game(GameSession(state), ["hero_arien", "hero_wasp"])


def _unload_idle(registry: GameRegistry, idle_seconds: float = 0) -> int:
    return asyncio.run(registry.unload_idle_finished_games(idle_seconds=idle_seconds))


def test_idle_finished_game_is_unloaded_but_save_stays(registry, tmp_path):
    game = _new_game(registry)
    _finish(registry, game.game_id)

    assert _unload_idle(registry) == 1

    assert not registry.is_loaded(game.game_id)
    assert (tmp_path / f"{game.game_id}.json").is_file()


def test_unloaded_game_tokens_still_resolve(registry):
    game = _new_game(registry)
    token = game.hero_to_token["hero_arien"]
    _finish(registry, game.game_id)
    _unload_idle(registry)

    assert registry.resolve_token(token) == (game.game_id, "hero_arien", False)
    assert registry.resolve_token(game.spectator_token) == (game.game_id, "", True)


def test_get_loads_unloaded_game_back(registry):
    game = _new_game(registry)
    _finish(registry, game.game_id)
    _unload_idle(registry)

    reloaded = registry.get(game.game_id)

    assert registry.is_loaded(game.game_id)
    assert reloaded.session.state.winner == TeamColor.RED
    assert reloaded.hero_to_token == game.hero_to_token
    assert reloaded.last_result is not None and reloaded.last_result.winner == "RED"


def test_unfinished_game_stays_loaded(registry):
    game = _new_game(registry)

    assert _unload_idle(registry) == 0
    assert registry.is_loaded(game.game_id)


def test_recently_viewed_finished_game_stays_loaded(registry):
    game = _new_game(registry)
    _finish(registry, game.game_id)
    registry.get(game.game_id)

    assert _unload_idle(registry, idle_seconds=3600) == 0
    assert registry.is_loaded(game.game_id)


def test_finished_game_with_open_socket_stays_loaded(registry):
    game = _new_game(registry)
    _finish(registry, game.game_id)
    game.spectator_ws_connections[1] = object()  # type: ignore[assignment]

    assert _unload_idle(registry) == 0
    assert registry.is_loaded(game.game_id)


def test_stale_unloaded_game_is_deleted(registry, tmp_path):
    game = _new_game(registry)
    _finish(registry, game.game_id)
    _unload_idle(registry)
    save = tmp_path / f"{game.game_id}.json"
    old = time.time() - 10 * 86400
    os.utime(save, (old, old))

    assert registry.cleanup_stale_games(max_age_seconds=5 * 86400) == 1

    assert not save.exists()
    assert registry.resolve_token(game.spectator_token) is None
    with pytest.raises(GameNotFoundError):
        registry.get(game.game_id)


def test_unloaded_game_with_missing_save_is_not_found(registry, tmp_path):
    game = _new_game(registry)
    _finish(registry, game.game_id)
    _unload_idle(registry)
    (tmp_path / f"{game.game_id}.json").unlink()

    with pytest.raises(GameNotFoundError):
        registry.get(game.game_id)
    assert registry.resolve_token(game.spectator_token) is None


# ---------------------------------------------------------------------------
# Startup: finished games are not loaded, but stay reachable
# ---------------------------------------------------------------------------


def _make_client(save_dir: str) -> TestClient:
    os.environ["GOA2_SAVE_DIR"] = save_dir
    return TestClient(create_app())


def _create_and_finish(client: TestClient) -> dict:
    resp = client.post(
        "/games",
        json={"map_name": "forgotten_island", "red_heroes": ["Arien"], "blue_heroes": ["Wasp"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    _finish(client.app.state.registry, data["game_id"])
    return data


def test_finished_game_is_not_loaded_at_startup(tmp_path):
    with _make_client(str(tmp_path)) as client1:
        finished = _create_and_finish(client1)
        resp = client1.post(
            "/games",
            json={"map_name": "forgotten_island", "red_heroes": ["Arien"], "blue_heroes": ["Wasp"]},
        )
        live_id = resp.json()["game_id"]

    with _make_client(str(tmp_path)) as client2:
        registry = client2.app.state.registry
        assert not registry.is_loaded(finished["game_id"])
        assert registry.is_loaded(live_id)

        response = client2.get(
            f"/games/{finished['game_id']}", headers=_auth(finished["spectator_token"])
        )
        assert response.status_code == 200
        assert response.json()["winner"] == "RED"
        assert registry.is_loaded(finished["game_id"])


def test_unloaded_game_reloads_on_websocket_connect(tmp_path):
    with _make_client(str(tmp_path)) as client1:
        finished = _create_and_finish(client1)

    with _make_client(str(tmp_path)) as client2:
        url = f"/games/{finished['game_id']}/ws?token={finished['spectator_token']}"
        with client2.websocket_connect(url) as websocket:
            message = websocket.receive_json()
            assert message["type"] == "STATE_UPDATE"
            assert message["winner"] == "RED"


def test_unloaded_game_keeps_its_logs_across_restart(tmp_path):
    with _make_client(str(tmp_path)) as client1:
        finished = _create_and_finish(client1)
    log_file = os.path.join(os.environ["GOA2_LOG_DIR"], f"{finished['game_id']}.log")
    assert os.path.exists(log_file)

    with _make_client(str(tmp_path)):
        assert os.path.exists(log_file)
