"""Per-mutation timing instrumentation on the WebSocket path."""

import os

import pytest
from fastapi.testclient import TestClient

from goa2.server.app import create_app
from goa2.server.game_logger import GameLogger


@pytest.fixture
def client(tmp_path):
    os.environ["GOA2_SAVE_DIR"] = str(tmp_path)
    app = create_app()
    with TestClient(app) as c:
        yield c
    os.environ.pop("GOA2_SAVE_DIR", None)


@pytest.fixture
def game_data(client):
    return client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
        },
    ).json()


def _token_for(game_data: dict, hero_id: str) -> str:
    return next(pt["token"] for pt in game_data["player_tokens"] if pt["hero_id"] == hero_id)


def _timing_events(log_dir: str, game_id: str) -> list[dict]:
    with open(os.path.join(log_dir, f"{game_id}.log")) as f:
        return [line for line in f if "TIMING:" in line]


def test_log_timing_records_each_phase(tmp_path):
    gl = GameLogger("g1", log_dir=str(tmp_path))
    gl.log_timing("SUBMIT_INPUT", engine_ms=17.5, fanout_ms=31.2, send_ms=2.0, clients=4)

    event = next(e for e in gl.events if e["type"] == "TIMING")
    assert event["data"] == {
        "action": "SUBMIT_INPUT",
        "engine_ms": 17.5,
        "fanout_ms": 31.2,
        "send_ms": 2.0,
        "total_ms": 50.7,
        "clients": 4,
    }

    text = (tmp_path / "g1.log").read_text()
    assert "TIMING: SUBMIT_INPUT" in text
    assert "engine=17.5ms" in text
    assert "clients=4" in text


def test_total_is_the_sum_of_the_phases(tmp_path):
    gl = GameLogger("g2", log_dir=str(tmp_path))
    gl.log_timing("COMMIT_CARD", engine_ms=1.0, fanout_ms=2.0, send_ms=3.0, clients=1)
    event = next(e for e in gl.events if e["type"] == "TIMING")
    assert event["data"]["total_ms"] == 6.0


def test_ws_mutation_emits_timing(client, game_data):
    game_id = game_data["game_id"]
    token = _token_for(game_data, "hero_arien")
    log_dir = os.environ["GOA2_LOG_DIR"]

    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        view = ws.receive_json()["view"]
        arien = next(
            hero
            for team in view["teams"].values()
            for hero in team["heroes"]
            if hero["id"] == "hero_arien"
        )
        ws.send_json({"type": "COMMIT_CARD", "card_id": arien["hand"][0]["id"]})
        assert ws.receive_json()["type"] == "ACTION_RESULT"
        assert ws.receive_json()["type"] == "STATE_UPDATE"

    lines = _timing_events(log_dir, game_id)
    assert lines, "a mutation must record a TIMING line"
    assert "COMMIT_CARD" in lines[-1]
    assert "clients=1" in lines[-1]


def test_get_view_is_not_timed(client, game_data):
    """GET_VIEW mutates nothing and fans out to nobody, so it records no timing."""
    game_id = game_data["game_id"]
    token = _token_for(game_data, "hero_arien")
    log_dir = os.environ["GOA2_LOG_DIR"]

    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "GET_VIEW"})
        assert ws.receive_json()["type"] == "STATE_UPDATE"

    assert not _timing_events(log_dir, game_id)
