"""WebSocket integration tests."""

import os

import pytest
from fastapi.testclient import TestClient

from goa2.server.app import create_app


@pytest.fixture
def client(tmp_path):
    os.environ["GOA2_SAVE_DIR"] = str(tmp_path)
    app = create_app()
    with TestClient(app) as c:
        yield c
    os.environ.pop("GOA2_SAVE_DIR", None)


@pytest.fixture
def game_data(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
        },
    )
    return resp.json()


def _token_for(game_data: dict, hero_id: str) -> str:
    for pt in game_data["player_tokens"]:
        if pt["hero_id"] == hero_id:
            return pt["token"]
    raise ValueError(f"No token for {hero_id}")


# ---- Connection tests ----


def test_ws_connect_and_receive_initial_state(client, game_data):
    token = _token_for(game_data, "hero_arien")
    game_id = game_data["game_id"]
    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "STATE_UPDATE"
        assert msg["view"]["phase"] == "PLANNING"


def test_ws_connect_spectator(client, game_data):
    game_id = game_data["game_id"]
    token = game_data["spectator_token"]
    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "STATE_UPDATE"


def test_ws_invalid_token(client, game_data):
    game_id = game_data["game_id"]
    with pytest.raises(Exception):
        with client.websocket_connect(f"/games/{game_id}/ws?token=badtoken") as ws:
            ws.receive_json()


def test_ws_wrong_game(client, game_data):
    token = _token_for(game_data, "hero_arien")
    with pytest.raises(Exception):
        with client.websocket_connect(f"/games/wrong_game/ws?token={token}") as ws:
            ws.receive_json()


# ---- GET_VIEW ----


def test_ws_get_view(client, game_data):
    token = _token_for(game_data, "hero_arien")
    game_id = game_data["game_id"]
    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        ws.receive_json()  # initial state
        ws.send_json({"type": "GET_VIEW"})
        msg = ws.receive_json()
        assert msg["type"] == "STATE_UPDATE"


# ---- Invalid JSON ----


def test_ws_invalid_json(client, game_data):
    token = _token_for(game_data, "hero_arien")
    game_id = game_data["game_id"]
    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        ws.receive_json()  # initial state
        ws.send_text("not json")
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert "Invalid JSON" in msg["detail"]


# ---- Unknown message type ----


def test_ws_unknown_type(client, game_data):
    token = _token_for(game_data, "hero_arien")
    game_id = game_data["game_id"]
    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        ws.receive_json()  # initial state
        ws.send_json({"type": "FOOBAR"})
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert "Unknown" in msg["detail"]


# ---- Spectator restrictions ----


def test_ws_spectator_cannot_commit_card(client, game_data):
    game_id = game_data["game_id"]
    token = game_data["spectator_token"]
    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "COMMIT_CARD", "card_id": "x"})
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert "Spectator" in msg["detail"]


def test_ws_spectator_can_get_view(client, game_data):
    game_id = game_data["game_id"]
    token = game_data["spectator_token"]
    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "GET_VIEW"})
        msg = ws.receive_json()
        assert msg["type"] == "STATE_UPDATE"


# ---- COMMIT_CARD via WS ----


def test_ws_commit_card(client, game_data):
    game_id = game_data["game_id"]
    token = _token_for(game_data, "hero_arien")

    # Get a card ID from REST
    view = client.get(
        f"/games/{game_id}", headers={"Authorization": f"Bearer {token}"}
    ).json()
    arien_hand = None
    for team_data in view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == "hero_arien":
                arien_hand = hero["hand"]
    assert arien_hand

    card_id = arien_hand[0]["id"]

    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as ws:
        ws.receive_json()  # initial state
        ws.send_json({"type": "COMMIT_CARD", "card_id": card_id})
        msg = ws.receive_json()
        assert msg["type"] == "ACTION_RESULT"
        assert msg["result_type"] in ("ACTION_COMPLETE", "PHASE_CHANGED", "INPUT_NEEDED")


# ---- Full WS flow ----


def test_ws_full_planning_flow(client, game_data):
    """Both players commit cards via WS."""
    game_id = game_data["game_id"]
    arien_token = _token_for(game_data, "hero_arien")
    wasp_token = _token_for(game_data, "hero_wasp")

    # Get card IDs via REST
    arien_view = client.get(
        f"/games/{game_id}", headers={"Authorization": f"Bearer {arien_token}"}
    ).json()
    wasp_view = client.get(
        f"/games/{game_id}", headers={"Authorization": f"Bearer {wasp_token}"}
    ).json()

    arien_card = wasp_card = None
    for team_data in arien_view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == "hero_arien":
                arien_card = hero["hand"][0]["id"]
    for team_data in wasp_view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == "hero_wasp":
                wasp_card = hero["hand"][0]["id"]

    assert arien_card and wasp_card

    # Arien commits
    with client.websocket_connect(f"/games/{game_id}/ws?token={arien_token}") as ws_a:
        ws_a.receive_json()  # initial
        ws_a.send_json({"type": "COMMIT_CARD", "card_id": arien_card})
        msg = ws_a.receive_json()
        assert msg["type"] == "ACTION_RESULT"
        assert msg["result_type"] == "ACTION_COMPLETE"

    # Wasp commits -> phase transition
    with client.websocket_connect(f"/games/{game_id}/ws?token={wasp_token}") as ws_w:
        ws_w.receive_json()  # initial
        ws_w.send_json({"type": "COMMIT_CARD", "card_id": wasp_card})
        msg = ws_w.receive_json()
        assert msg["type"] == "ACTION_RESULT"
        assert msg["current_phase"] != "PLANNING"
