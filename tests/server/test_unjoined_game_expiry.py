"""Games no player ever connected to are deleted a day after creation."""

import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goa2.domain.models import GamePhase, TeamColor
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.server.app import create_app
from goa2.server.errors import GameNotFoundError
from goa2.server.registry import UNJOINED_GAME_TTL_SECONDS, GameRegistry

MAP_PATH = "src/goa2/data/maps/forgotten_island.json"
GAME_BODY = {"map_name": "forgotten_island", "red_heroes": ["Arien"], "blue_heroes": ["Wasp"]}


@pytest.fixture
def registry(tmp_path):
    return GameRegistry(save_dir=str(tmp_path))


def _new_game(registry: GameRegistry, age_seconds: float = 2 * UNJOINED_GAME_TTL_SECONDS):
    state = GameSetup.create_game(MAP_PATH, ["Arien"], ["Wasp"])
    game = registry.create_game(GameSession(state), ["hero_arien", "hero_wasp"])
    game.created_at = time.time() - age_seconds
    return game


def _expire(registry: GameRegistry) -> int:
    return asyncio.run(registry.expire_unjoined_games())


def _log_files(game_id: str) -> list[Path]:
    return list(Path(os.environ["GOA2_LOG_DIR"]).glob(f"{game_id}*"))


def test_old_unjoined_game_is_deleted_with_its_files(registry, tmp_path):
    game = _new_game(registry)
    game.replay_recorder.record_setup(
        map_name="forgotten_island",
        red_heroes=["Arien"],
        blue_heroes=["Wasp"],
        game_type="QUICK",
        cheats=False,
        seed=1,
    )
    game.game_logger.log_ws_connect(None, True)
    replay_path = game.replay_recorder.path
    assert replay_path.is_file()
    assert _log_files(game.game_id)

    assert _expire(registry) == 1

    assert not (tmp_path / f"{game.game_id}.json").exists()
    assert not replay_path.exists()
    assert _log_files(game.game_id) == []
    assert registry.resolve_token(game.spectator_token) is None
    with pytest.raises(GameNotFoundError):
        registry.get(game.game_id)


def test_young_unjoined_game_is_kept(registry):
    game = _new_game(registry, age_seconds=UNJOINED_GAME_TTL_SECONDS - 60)

    assert _expire(registry) == 0
    assert registry.is_loaded(game.game_id)


def test_joined_game_is_kept(registry):
    game = _new_game(registry)
    game.joined = True

    assert _expire(registry) == 0
    assert registry.is_loaded(game.game_id)


def test_unjoined_game_with_open_socket_is_kept(registry):
    game = _new_game(registry)
    game.spectator_ws_connections[1] = object()  # type: ignore[assignment]

    assert _expire(registry) == 0
    assert registry.is_loaded(game.game_id)


def test_game_with_a_recorded_decision_counts_as_joined(registry):
    game = _new_game(registry)
    game.replay_recorder.record_pass("hero_arien", round_num=1, turn=1)

    assert _expire(registry) == 0
    assert registry.is_loaded(game.game_id)


def test_finished_game_is_never_expired(registry):
    game = _new_game(registry)
    game.session.state.phase = GamePhase.GAME_OVER
    game.session.state.winner = TeamColor.RED

    assert _expire(registry) == 0
    assert registry.is_loaded(game.game_id)


def test_unloaded_finished_game_is_untouched(registry, tmp_path):
    game = _new_game(registry)
    state = game.session.state
    state.phase = GamePhase.GAME_OVER
    state.winner = TeamColor.RED
    state.execution_stack.clear()
    registry.save_game(game.game_id)
    asyncio.run(registry.unload_idle_finished_games(idle_seconds=0))

    assert _expire(registry) == 0
    assert (tmp_path / f"{game.game_id}.json").is_file()
    assert registry.resolve_token(game.spectator_token) is not None


def test_save_without_joined_flag_restores_as_joined(registry, tmp_path):
    game = _new_game(registry)
    save = tmp_path / f"{game.game_id}.json"
    payload = json.loads(save.read_text())
    assert payload["joined"] is False
    del payload["joined"]
    payload["created_at"] = time.time() - 10 * UNJOINED_GAME_TTL_SECONDS
    save.write_text(json.dumps(payload))

    restored = GameRegistry(save_dir=str(tmp_path))
    restored.restore_all()

    assert asyncio.run(restored.expire_unjoined_games()) == 0
    assert restored.get(game.game_id).joined is True


# ---------------------------------------------------------------------------
# Over the server: only a player WebSocket marks a game joined
# ---------------------------------------------------------------------------


def _make_client(save_dir: str) -> TestClient:
    os.environ["GOA2_SAVE_DIR"] = save_dir
    return TestClient(create_app())


def _backdate(save_dir: Path, game_id: str) -> None:
    save = save_dir / f"{game_id}.json"
    payload = json.loads(save.read_text())
    payload["created_at"] = time.time() - 2 * UNJOINED_GAME_TTL_SECONDS
    save.write_text(json.dumps(payload))


def test_player_websocket_marks_game_joined_across_restart(tmp_path):
    with _make_client(str(tmp_path)) as client1:
        data = client1.post("/games", json=GAME_BODY).json()
        token = data["player_tokens"][0]["token"]
        with client1.websocket_connect(f"/games/{data['game_id']}/ws?token={token}") as ws:
            assert ws.receive_json()["type"] == "STATE_UPDATE"
        assert json.loads((tmp_path / f"{data['game_id']}.json").read_text())["joined"] is True
    _backdate(tmp_path, data["game_id"])

    with _make_client(str(tmp_path)) as client2:
        registry = client2.app.state.registry
        assert asyncio.run(registry.expire_unjoined_games()) == 0
        assert registry.is_loaded(data["game_id"])


def test_spectator_websocket_and_rest_polling_do_not_join(tmp_path):
    with _make_client(str(tmp_path)) as client1:
        data = client1.post("/games", json=GAME_BODY).json()
        token = data["player_tokens"][0]["token"]
        auth = {"Authorization": f"Bearer {token}"}
        assert client1.get(f"/games/{data['game_id']}", headers=auth).status_code == 200
        spectate = f"/games/{data['game_id']}/ws?token={data['spectator_token']}"
        with client1.websocket_connect(spectate) as ws:
            assert ws.receive_json()["type"] == "STATE_UPDATE"
    _backdate(tmp_path, data["game_id"])

    with _make_client(str(tmp_path)) as client2:
        registry = client2.app.state.registry
        assert asyncio.run(registry.expire_unjoined_games()) == 1
        assert client2.get(f"/games/{data['game_id']}", headers=auth).status_code == 401
