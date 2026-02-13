"""REST integration tests using FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient

from goa2.server.app import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def game_data(client):
    """Create a game and return (response_json, client)."""
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _token_for(game_data: dict, hero_id: str) -> str:
    for pt in game_data["player_tokens"]:
        if pt["hero_id"] == hero_id:
            return pt["token"]
    raise ValueError(f"No token for {hero_id}")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- /heroes ----


def test_list_heroes(client):
    resp = client.get("/heroes")
    assert resp.status_code == 200
    heroes = resp.json()
    assert isinstance(heroes, list)
    assert "Arien" in heroes


# ---- POST /games ----


def test_create_game(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "game_id" in data
    assert len(data["player_tokens"]) == 2
    assert data["spectator_token"]


def test_create_game_bad_map(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "nonexistent_map",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
        },
    )
    assert resp.status_code == 404


# ---- GET /games/{game_id} ----


def test_get_game_view(client, game_data):
    token = _token_for(game_data, "hero_arien")
    resp = client.get(
        f"/games/{game_data['game_id']}", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "view" in body
    assert body["view"]["phase"] == "PLANNING"


def test_get_game_view_spectator(client, game_data):
    resp = client.get(
        f"/games/{game_data['game_id']}",
        headers=_auth(game_data["spectator_token"]),
    )
    assert resp.status_code == 200


def test_get_game_view_no_auth(client, game_data):
    resp = client.get(f"/games/{game_data['game_id']}")
    assert resp.status_code == 401


def test_get_game_view_wrong_game(client, game_data):
    token = _token_for(game_data, "hero_arien")
    resp = client.get("/games/wrong_id", headers=_auth(token))
    assert resp.status_code == 403


# ---- POST /games/{game_id}/cards ----


def test_commit_card(client, game_data):
    """Commit a card during PLANNING."""
    token = _token_for(game_data, "hero_arien")
    game_id = game_data["game_id"]

    # Get view to find a card
    view = client.get(f"/games/{game_id}", headers=_auth(token)).json()
    arien_cards = None
    for team_data in view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == "hero_arien":
                arien_cards = hero["hand"]
                break
    assert arien_cards and len(arien_cards) > 0

    card_id = arien_cards[0]["id"]
    resp = client.post(
        f"/games/{game_id}/cards",
        json={"card_id": card_id},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result_type"] in ("ACTION_COMPLETE", "PHASE_CHANGED", "INPUT_NEEDED")


def test_commit_card_bad_id(client, game_data):
    token = _token_for(game_data, "hero_arien")
    resp = client.post(
        f"/games/{game_data['game_id']}/cards",
        json={"card_id": "nonexistent_card"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


def test_commit_card_spectator_forbidden(client, game_data):
    resp = client.post(
        f"/games/{game_data['game_id']}/cards",
        json={"card_id": "some_card"},
        headers=_auth(game_data["spectator_token"]),
    )
    assert resp.status_code == 403


# ---- POST /games/{game_id}/pass ----


def test_pass_turn_spectator_forbidden(client, game_data):
    resp = client.post(
        f"/games/{game_data['game_id']}/pass",
        headers=_auth(game_data["spectator_token"]),
    )
    assert resp.status_code == 403


# ---- POST /games/{game_id}/input ----


def test_submit_input_spectator_forbidden(client, game_data):
    resp = client.post(
        f"/games/{game_data['game_id']}/input",
        json={"request_id": "", "selection": "x"},
        headers=_auth(game_data["spectator_token"]),
    )
    assert resp.status_code == 403


# ---- POST /games/{game_id}/advance ----


def test_advance_spectator_forbidden(client, game_data):
    resp = client.post(
        f"/games/{game_data['game_id']}/advance",
        headers=_auth(game_data["spectator_token"]),
    )
    assert resp.status_code == 403


# ---- Full flow: commit both cards -> phase transition ----


def test_full_planning_flow(client, game_data):
    """Both players commit cards, triggering phase transition."""
    game_id = game_data["game_id"]
    arien_token = _token_for(game_data, "hero_arien")
    wasp_token = _token_for(game_data, "hero_wasp")

    # Get Arien's cards
    view = client.get(f"/games/{game_id}", headers=_auth(arien_token)).json()
    arien_hand = None
    for team_data in view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == "hero_arien":
                arien_hand = hero["hand"]
    assert arien_hand

    # Get Wasp's cards
    view = client.get(f"/games/{game_id}", headers=_auth(wasp_token)).json()
    wasp_hand = None
    for team_data in view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == "hero_wasp":
                wasp_hand = hero["hand"]
    assert wasp_hand

    # Commit Arien's card
    resp1 = client.post(
        f"/games/{game_id}/cards",
        json={"card_id": arien_hand[0]["id"]},
        headers=_auth(arien_token),
    )
    assert resp1.status_code == 200
    assert resp1.json()["result_type"] == "ACTION_COMPLETE"

    # Commit Wasp's card -> triggers phase transition
    resp2 = client.post(
        f"/games/{game_id}/cards",
        json={"card_id": wasp_hand[0]["id"]},
        headers=_auth(wasp_token),
    )
    assert resp2.status_code == 200
    # After both commit, phase should change
    body = resp2.json()
    assert body["current_phase"] != "PLANNING"
