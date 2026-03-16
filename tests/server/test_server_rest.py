"""REST integration tests using FastAPI TestClient."""

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
    resp = client.get(f"/games/{game_data['game_id']}", headers=_auth(token))
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


# ---- Cheats ----


def test_create_game_with_cheats_enabled(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "cheats_enabled": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()

    # Verify cheats_enabled is in the view
    arien_token = _token_for(data, "hero_arien")
    view_resp = client.get(f"/games/{data['game_id']}", headers=_auth(arien_token))
    assert view_resp.status_code == 200
    view = view_resp.json()
    assert view["view"]["cheats_enabled"] is True


def test_create_game_without_cheats(client):
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

    # Verify cheats_enabled defaults to False
    arien_token = _token_for(data, "hero_arien")
    view_resp = client.get(f"/games/{data['game_id']}", headers=_auth(arien_token))
    assert view_resp.status_code == 200
    view = view_resp.json()
    assert view["view"]["cheats_enabled"] is False


def test_give_gold_cheat_success(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "cheats_enabled": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    game_id = data["game_id"]
    arien_token = _token_for(data, "hero_arien")

    # Give gold to Arien
    cheat_resp = client.post(
        f"/games/{game_id}/cheats/gold",
        json={"hero_id": "hero_arien", "amount": 5},
        headers=_auth(arien_token),
    )
    assert cheat_resp.status_code == 200
    result = cheat_resp.json()
    assert result["result_type"] == "ACTION_COMPLETE"
    assert result["events"]
    assert result["events"][0]["event_type"] == "GOLD_GAINED"
    assert result["events"][0]["metadata"]["amount"] == 5
    assert result["events"][0]["metadata"]["reason"] == "cheat"

    # Verify gold was added
    view_resp = client.get(f"/games/{game_id}", headers=_auth(arien_token))
    view = view_resp.json()
    arien_gold = None
    for team_data in view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == "hero_arien":
                arien_gold = hero["gold"]
    assert arien_gold == 5


def test_give_gold_cheat_disabled(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "cheats_enabled": False,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    game_id = data["game_id"]
    arien_token = _token_for(data, "hero_arien")

    # Try to give gold when cheats are disabled
    cheat_resp = client.post(
        f"/games/{game_id}/cheats/gold",
        json={"hero_id": "hero_arien", "amount": 5},
        headers=_auth(arien_token),
    )
    assert cheat_resp.status_code == 403
    assert "Cheats are not enabled" in cheat_resp.json()["detail"]


def test_give_gold_cheat_wrong_phase(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "cheats_enabled": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    game_id = data["game_id"]
    arien_token = _token_for(data, "hero_arien")
    wasp_token = _token_for(data, "hero_wasp")

    # Get Arien's hand
    view_resp = client.get(f"/games/{game_id}", headers=_auth(arien_token))
    view = view_resp.json()
    arien_card_id = None
    for team_data in view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == "hero_arien" and hero["hand"]:
                arien_card_id = hero["hand"][0]["id"]

    # Get Wasp's hand
    view_resp = client.get(f"/games/{game_id}", headers=_auth(wasp_token))
    view = view_resp.json()
    wasp_card_id = None
    for team_data in view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == "hero_wasp" and hero["hand"]:
                wasp_card_id = hero["hand"][0]["id"]

    # Both players commit cards to move to REVELATION phase
    client.post(
        f"/games/{game_id}/cards",
        json={"card_id": arien_card_id},
        headers=_auth(arien_token),
    )
    client.post(
        f"/games/{game_id}/cards",
        json={"card_id": wasp_card_id},
        headers=_auth(wasp_token),
    )

    # Try to give gold in non-PLANNING phase
    cheat_resp = client.post(
        f"/games/{game_id}/cheats/gold",
        json={"hero_id": "hero_arien", "amount": 5},
        headers=_auth(arien_token),
    )
    assert cheat_resp.status_code == 409
    assert "Expected phase PLANNING" in cheat_resp.json()["detail"]


def test_give_gold_cheat_invalid_hero(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "cheats_enabled": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    game_id = data["game_id"]
    arien_token = _token_for(data, "hero_arien")

    # Try to give gold to non-existent hero
    cheat_resp = client.post(
        f"/games/{game_id}/cheats/gold",
        json={"hero_id": "hero_does_not_exist", "amount": 5},
        headers=_auth(arien_token),
    )
    assert cheat_resp.status_code == 404


def test_give_gold_cheat_negative_amount(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "cheats_enabled": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    game_id = data["game_id"]
    arien_token = _token_for(data, "hero_arien")

    # Try to give negative gold
    cheat_resp = client.post(
        f"/games/{game_id}/cheats/gold",
        json={"hero_id": "hero_arien", "amount": -5},
        headers=_auth(arien_token),
    )
    assert cheat_resp.status_code == 400
    assert "Amount must be a positive integer" in cheat_resp.json()["detail"]


# ---- POST /games/{game_id}/rollback ----


def _advance_to_resolution(client, game_data):
    """Commit cards for both players to transition to RESOLUTION, return tokens."""
    game_id = game_data["game_id"]
    arien_token = _token_for(game_data, "hero_arien")
    wasp_token = _token_for(game_data, "hero_wasp")

    # Get hands
    view = client.get(f"/games/{game_id}", headers=_auth(arien_token)).json()
    arien_card = None
    for td in view["view"]["teams"].values():
        for h in td["heroes"]:
            if h["id"] == "hero_arien" and h["hand"]:
                arien_card = h["hand"][0]["id"]

    view = client.get(f"/games/{game_id}", headers=_auth(wasp_token)).json()
    wasp_card = None
    for td in view["view"]["teams"].values():
        for h in td["heroes"]:
            if h["id"] == "hero_wasp" and h["hand"]:
                wasp_card = h["hand"][0]["id"]

    # Commit both
    client.post(f"/games/{game_id}/cards", json={"card_id": arien_card}, headers=_auth(arien_token))
    client.post(f"/games/{game_id}/cards", json={"card_id": wasp_card}, headers=_auth(wasp_token))
    return arien_token, wasp_token


def test_rollback_spectator_forbidden(client, game_data):
    resp = client.post(
        f"/games/{game_data['game_id']}/rollback",
        headers=_auth(game_data["spectator_token"]),
    )
    assert resp.status_code == 403


def test_rollback_no_active_resolution(client, game_data):
    """Rollback fails when there's no active resolution."""
    token = _token_for(game_data, "hero_arien")
    resp = client.post(
        f"/games/{game_data['game_id']}/rollback",
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_rollback_not_current_actor(client, game_data):
    """Only the current actor can rollback."""
    game_id = game_data["game_id"]
    arien_token, wasp_token = _advance_to_resolution(client, game_data)

    # Check who the current actor is from the input_request
    view = client.get(f"/games/{game_id}", headers=_auth(arien_token)).json()
    ir = view.get("input_request")
    if ir:
        current_actor = ir["player_id"]
        non_actor_token = wasp_token if current_actor == "hero_arien" else arien_token
        resp = client.post(
            f"/games/{game_id}/rollback",
            headers=_auth(non_actor_token),
        )
        assert resp.status_code == 403


def test_give_gold_cheat_spectator_blocked(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "cheats_enabled": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    game_id = data["game_id"]
    spectator_token = data["spectator_token"]

    # Try to use cheats as spectator
    cheat_resp = client.post(
        f"/games/{game_id}/cheats/gold",
        json={"hero_id": "hero_arien", "amount": 5},
        headers=_auth(spectator_token),
    )
    assert cheat_resp.status_code == 403
    assert "Spectators cannot use cheats" in cheat_resp.json()["detail"]
