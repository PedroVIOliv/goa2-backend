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
    assert "Cordelia" not in heroes


def test_list_heroes_can_include_playtest_heroes(client):
    resp = client.get("/heroes", params={"include_playtest": True})

    assert resp.status_code == 200
    assert "Cordelia" in resp.json()


def test_list_hero_metadata_includes_difficulty_stars(client):
    resp = client.get("/heroes/metadata")
    assert resp.status_code == 200
    heroes = {hero["id"]: hero["difficulty_stars"] for hero in resp.json()}

    assert heroes == {
        "Arien": 1,
        "Xargatha": 1,
        "Wasp": 1,
        "Brogan": 1,
        "Tigerclaw": 1,
        "Sabina": 1,
        "Dodger": 1,
        "Bain": 2,
        "Whisper": 2,
        "Rowenna": 2,
        "Ursafar": 2,
        "Min": 2,
        "Misa": 2,
        "Garrus": 2,
        "Silverarrow": 2,
        "Mortimer": 3,
        "Widget": 3,
        "Trinkets": 3,
        "Tali": 3,
        "Wuk": 3,
        "Swift": 3,
        "Mrak": 3,
        "Cutter": 3,
        "Hanu": 3,
        "Brynn": 3,
        "Razzle": 4,
        "Ignatia": 4,
        "Emmitt": 4,
        "Gydion": 4,
        "NebKher": 4,
        "Snorri": 4,
        "Takahide": 4,
    }


def test_list_hero_metadata_can_include_playtest_heroes(client):
    resp = client.get("/heroes/metadata", params={"include_playtest": True})

    assert resp.status_code == 200
    heroes = {hero["id"]: hero["difficulty_stars"] for hero in resp.json()}
    assert heroes["Cordelia"] == 2


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


def test_create_quick_game(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "game_type": "QUICK",
        },
    )
    assert resp.status_code == 201
    data = resp.json()

    token = _token_for(data, "hero_arien")
    view_resp = client.get(f"/games/{data['game_id']}", headers=_auth(token))
    assert view_resp.status_code == 200
    view = view_resp.json()["view"]

    assert view["teams"]["RED"]["life_counters"] == 3
    assert view["teams"]["BLUE"]["life_counters"] == 3


def test_create_uneven_player_game_uses_upper_life_count(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien", "Min"],
            "blue_heroes": ["Wasp"],
            "game_type": "QUICK",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["player_tokens"]) == 3

    token = _token_for(data, "hero_arien")
    view_resp = client.get(f"/games/{data['game_id']}", headers=_auth(token))
    assert view_resp.status_code == 200
    view = view_resp.json()["view"]

    assert view["teams"]["RED"]["life_counters"] == 4
    assert view["teams"]["BLUE"]["life_counters"] == 4


def test_create_game_invalid_game_type(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "game_type": "BLITZ",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid game_type 'BLITZ'. Must be QUICK or LONG."


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


def test_get_game_view_names_the_awaited_player_to_a_non_responder(client, game_data):
    from goa2.domain.input import InputRequestType, create_input_request
    from goa2.engine.session import SessionResult, SessionResultType

    game = client.app.state.registry.get(game_data["game_id"])
    game.last_result = SessionResult(
        result_type=SessionResultType.INPUT_NEEDED,
        current_phase=game.session.state.phase,
        input_request=create_input_request(
            InputRequestType.SELECT_CARD_OR_PASS,
            player_id="hero_wasp",
            prompt="Choose a defense",
            options=[{"id": "magnetic_dagger", "text": "Magnetic Dagger"}],
        ),
    )

    resp = client.get(
        f"/games/{game_data['game_id']}",
        headers=_auth(_token_for(game_data, "hero_arien")),
    )
    body = resp.json()

    assert body["awaiting_input"] == ["hero_wasp"]
    assert body["input_request"] is None


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
        json={"request_id": "spectator-request", "selection": "x"},
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


def test_rollback_authorizes_controller_during_action_control(client, game_data):
    """Under Hanu's ultimate the action's inputs are remapped to the controller,
    who owns the confirm/rollback — not the controlled actor."""
    game_id = game_data["game_id"]
    _advance_to_resolution(client, game_data)

    registry = client.app.state.registry
    game = registry.get(game_id)
    session = game.session
    ir = game.last_result.input_request if game.last_result else None
    if ir is None or session.state.current_actor_id is None:
        pytest.skip("no active resolution input to remap")

    actor = str(session.state.current_actor_id)
    controller = "hero_wasp" if actor == "hero_arien" else "hero_arien"

    # Simulate the handler's control remap: the pending input is addressed to
    # the controller, the original actor is preserved in context, and a snapshot
    # was taken for the actor's action.
    ir.player_id = controller
    ir.context["controlled_hero_id"] = actor
    session._rollback_snapshot = session._make_snapshot()
    session._rollback_actor_id = actor

    # The controlled actor may NOT rollback the controlled action.
    resp_actor = client.post(
        f"/games/{game_id}/rollback", headers=_auth(_token_for(game_data, actor))
    )
    assert resp_actor.status_code == 403

    # The controller MAY rollback.
    resp_ctrl = client.post(
        f"/games/{game_id}/rollback", headers=_auth(_token_for(game_data, controller))
    )
    assert resp_ctrl.status_code == 200


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


# ---- Alternative Timelines (Emmitt ultimate) planning flow ----


@pytest.fixture
def emmitt_game(client):
    """Game with Emmitt (RED, level 8 → ultimate active) vs Wasp (BLUE)."""
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Emmitt"],
            "blue_heroes": ["Wasp"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    game = client.app.state.registry.get(data["game_id"])
    game.session.state.get_hero("hero_emmitt").level = 8
    return data


def _first_hand_card_id(client, game_data, hero_id):
    token = _token_for(game_data, hero_id)
    view = client.get(f"/games/{game_data['game_id']}", headers=_auth(token)).json()
    for team in view["view"]["teams"].values():
        for hero in team["heroes"]:
            if hero["id"] == hero_id:
                return hero["hand"][0]["id"]
    raise ValueError(f"No hand for {hero_id}")


def test_emmitt_two_card_commit_and_retrieve(client, emmitt_game):
    """Second commit accepted; after all commit, the retrieve prompt goes to
    Emmitt; answering it returns the card to hand and starts resolution."""
    game_id = emmitt_game["game_id"]
    em_token = _token_for(emmitt_game, "hero_emmitt")
    wa_token = _token_for(emmitt_game, "hero_wasp")

    r1 = client.post(
        f"/games/{game_id}/cards", json={"card_id": "reverse_time"}, headers=_auth(em_token)
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/games/{game_id}/cards", json={"card_id": "unstable_timeline"}, headers=_auth(em_token)
    )
    assert r2.status_code == 200

    wasp_card = _first_hand_card_id(client, emmitt_game, "hero_wasp")
    r3 = client.post(
        f"/games/{game_id}/cards", json={"card_id": wasp_card}, headers=_auth(wa_token)
    )
    assert r3.status_code == 200
    body = r3.json()
    assert body["current_phase"] == "RESOLUTION"
    # The final commit starts an Emmitt-only choice, which must not ride back
    # on Wasp's action response or appear in public/opponent state reads.
    assert body["input_request"] is None
    assert client.get(f"/games/{game_id}", headers=_auth(wa_token)).json()["input_request"] is None
    assert (
        client.get(f"/games/{game_id}", headers=_auth(emmitt_game["spectator_token"])).json()[
            "input_request"
        ]
        is None
    )

    owner_request = client.get(f"/games/{game_id}", headers=_auth(em_token)).json()["input_request"]
    assert owner_request["player_id"] == "hero_emmitt"
    assert set(owner_request["valid_options"]) == {
        "reverse_time",
        "unstable_timeline",
    }

    stale = client.post(
        f"/games/{game_id}/input",
        json={"request_id": "stale-request", "selection": "unstable_timeline"},
        headers=_auth(em_token),
    )
    assert stale.status_code == 400

    r4 = client.post(
        f"/games/{game_id}/input",
        json={
            "request_id": owner_request["request_id"],
            "selection": "unstable_timeline",
        },
        headers=_auth(em_token),
    )
    assert r4.status_code == 200

    view = client.get(f"/games/{game_id}", headers=_auth(em_token)).json()["view"]
    emmitt_view = next(
        h for t in view["teams"].values() for h in t["heroes"] if h["id"] == "hero_emmitt"
    )
    assert "unstable_timeline" in [c["id"] for c in emmitt_view["hand"]]
    assert emmitt_view["current_turn_card"]["id"] == "reverse_time"
    assert emmitt_view["extra_turn_card"] is None


def test_emmitt_planning_done_endpoint(client, emmitt_game):
    """Commit one + planning-done closes Emmitt's planning without a second card."""
    game_id = emmitt_game["game_id"]
    em_token = _token_for(emmitt_game, "hero_emmitt")
    wa_token = _token_for(emmitt_game, "hero_wasp")

    client.post(
        f"/games/{game_id}/cards", json={"card_id": "reverse_time"}, headers=_auth(em_token)
    )
    wasp_card = _first_hand_card_id(client, emmitt_game, "hero_wasp")
    r = client.post(f"/games/{game_id}/cards", json={"card_id": wasp_card}, headers=_auth(wa_token))
    assert r.json()["current_phase"] == "PLANNING"  # waits for Emmitt

    done = client.post(f"/games/{game_id}/planning-done", headers=_auth(em_token))
    assert done.status_code == 200
    assert done.json()["current_phase"] == "RESOLUTION"


def test_planning_done_before_commit_rejected(client, emmitt_game):
    game_id = emmitt_game["game_id"]
    em_token = _token_for(emmitt_game, "hero_emmitt")
    resp = client.post(f"/games/{game_id}/planning-done", headers=_auth(em_token))
    assert resp.status_code == 400


def _hero_view(client, game_id, token, hero_id):
    view = client.get(f"/games/{game_id}", headers=_auth(token)).json()["view"]
    return next(h for t in view["teams"].values() for h in t["heroes"] if h["id"] == hero_id)


def test_can_commit_second_card_flag(client, emmitt_game):
    """The own-hero view exposes can_commit_second_card across the two-card window."""
    game_id = emmitt_game["game_id"]
    em_token = _token_for(emmitt_game, "hero_emmitt")
    wa_token = _token_for(emmitt_game, "hero_wasp")

    # Before committing: not yet open.
    assert _hero_view(client, game_id, em_token, "hero_emmitt")["can_commit_second_card"] is False

    # After the first commit: open in Emmitt's own view...
    client.post(
        f"/games/{game_id}/cards", json={"card_id": "reverse_time"}, headers=_auth(em_token)
    )
    assert _hero_view(client, game_id, em_token, "hero_emmitt")["can_commit_second_card"] is True
    # ...but never leaked to the opponent's view of Emmitt.
    assert _hero_view(client, game_id, wa_token, "hero_emmitt")["can_commit_second_card"] is False

    # After the second commit: closed again.
    client.post(
        f"/games/{game_id}/cards", json={"card_id": "unstable_timeline"}, headers=_auth(em_token)
    )
    assert _hero_view(client, game_id, em_token, "hero_emmitt")["can_commit_second_card"] is False


def test_two_committed_cards_are_both_exposed_during_planning(client, emmitt_game):
    """The planning view uses extra_turn_card for the buffered first commit."""
    game_id = emmitt_game["game_id"]
    em_token = _token_for(emmitt_game, "hero_emmitt")
    wa_token = _token_for(emmitt_game, "hero_wasp")

    client.post(
        f"/games/{game_id}/cards", json={"card_id": "reverse_time"}, headers=_auth(em_token)
    )
    after_first = _hero_view(client, game_id, em_token, "hero_emmitt")
    assert after_first["current_turn_card"]["id"] == "reverse_time"
    assert after_first["extra_turn_card"] is None

    client.post(
        f"/games/{game_id}/cards",
        json={"card_id": "unstable_timeline"},
        headers=_auth(em_token),
    )

    owner_view = _hero_view(client, game_id, em_token, "hero_emmitt")
    assert owner_view["current_turn_card"]["id"] == "unstable_timeline"
    assert owner_view["extra_turn_card"]["id"] == "reverse_time"

    opponent_view = _hero_view(client, game_id, wa_token, "hero_emmitt")
    assert opponent_view["current_turn_card"]["is_facedown"] is True
    assert opponent_view["extra_turn_card"]["is_facedown"] is True
    assert "id" not in opponent_view["extra_turn_card"]


def test_can_commit_second_card_false_for_normal_hero(client, game_data):
    """A hero without the two-card ultimate never sees the flag set."""
    game_id = game_data["game_id"]
    token = _token_for(game_data, "hero_arien")
    assert _hero_view(client, game_id, token, "hero_arien")["can_commit_second_card"] is False
    card = _first_hand_card_id(client, game_data, "hero_arien")
    client.post(f"/games/{game_id}/cards", json={"card_id": card}, headers=_auth(token))
    assert _hero_view(client, game_id, token, "hero_arien")["can_commit_second_card"] is False


def test_second_commit_without_ultimate_still_409(client, game_data):
    """Regression: a normal hero's second commit is still rejected."""
    game_id = game_data["game_id"]
    token = _token_for(game_data, "hero_arien")
    card = _first_hand_card_id(client, game_data, "hero_arien")
    assert (
        client.post(
            f"/games/{game_id}/cards", json={"card_id": card}, headers=_auth(token)
        ).status_code
        == 200
    )
    view = client.get(f"/games/{game_id}", headers=_auth(token)).json()["view"]
    arien = next(h for t in view["teams"].values() for h in t["heroes"] if h["id"] == "hero_arien")
    second = arien["hand"][0]["id"]
    resp = client.post(f"/games/{game_id}/cards", json={"card_id": second}, headers=_auth(token))
    assert resp.status_code == 409


# ---- POST /games/{game_id}/uncommit ----


def _hero_view_of(client, game_id: str, token: str, hero_id: str) -> dict:
    view = client.get(f"/games/{game_id}", headers=_auth(token)).json()
    for team_data in view["view"]["teams"].values():
        for hero in team_data["heroes"]:
            if hero["id"] == hero_id:
                return hero
    raise ValueError(f"Hero {hero_id} not in view")


def test_uncommit_returns_card_to_hand(client, game_data):
    game_id = game_data["game_id"]
    token = _token_for(game_data, "hero_arien")

    hand = _hero_view_of(client, game_id, token, "hero_arien")["hand"]
    card_id = hand[0]["id"]
    hand_size = len(hand)

    resp = client.post(f"/games/{game_id}/cards", json={"card_id": card_id}, headers=_auth(token))
    assert resp.status_code == 200

    resp = client.post(f"/games/{game_id}/uncommit", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["current_phase"] == "PLANNING"

    hero = _hero_view_of(client, game_id, token, "hero_arien")
    assert hero["current_turn_card"] is None
    assert len(hero["hand"]) == hand_size
    assert any(c["id"] == card_id for c in hero["hand"])


def test_uncommit_then_commit_other_card(client, game_data):
    game_id = game_data["game_id"]
    token = _token_for(game_data, "hero_arien")

    hand = _hero_view_of(client, game_id, token, "hero_arien")["hand"]
    card0, card1 = hand[0]["id"], hand[1]["id"]

    client.post(f"/games/{game_id}/cards", json={"card_id": card0}, headers=_auth(token))
    client.post(f"/games/{game_id}/uncommit", headers=_auth(token))
    resp = client.post(f"/games/{game_id}/cards", json={"card_id": card1}, headers=_auth(token))
    assert resp.status_code == 200

    hero = _hero_view_of(client, game_id, token, "hero_arien")
    assert hero["current_turn_card"]["id"] == card1


def test_uncommit_nothing_committed_is_400(client, game_data):
    token = _token_for(game_data, "hero_arien")
    resp = client.post(f"/games/{game_data['game_id']}/uncommit", headers=_auth(token))
    assert resp.status_code == 400
    assert "no committed card" in resp.json()["detail"]


def test_uncommit_spectator_forbidden(client, game_data):
    resp = client.post(
        f"/games/{game_data['game_id']}/uncommit",
        headers=_auth(game_data["spectator_token"]),
    )
    assert resp.status_code == 403


def test_uncommit_after_lock_in_is_409(client, game_data):
    """Once the last commit fires revelation, a take-back gets a phase error."""
    game_id = game_data["game_id"]
    a_token = _token_for(game_data, "hero_arien")
    w_token = _token_for(game_data, "hero_wasp")

    a_card = _hero_view_of(client, game_id, a_token, "hero_arien")["hand"][0]["id"]
    w_card = _hero_view_of(client, game_id, w_token, "hero_wasp")["hand"][0]["id"]

    client.post(f"/games/{game_id}/cards", json={"card_id": a_card}, headers=_auth(a_token))
    client.post(f"/games/{game_id}/cards", json={"card_id": w_card}, headers=_auth(w_token))

    resp = client.post(f"/games/{game_id}/uncommit", headers=_auth(a_token))
    assert resp.status_code == 409


def test_create_game_accepts_player_names(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "player_names": {"Arien": "Tuck", "Wasp": "Wisdom"},
        },
    )
    assert resp.status_code == 201
    game = client.app.state.registry.get(resp.json()["game_id"])
    assert game.hero_names == {"hero_arien": "Tuck", "hero_wasp": "Wisdom"}


def test_create_game_without_player_names_stores_none(client, game_data):
    game = client.app.state.registry.get(game_data["game_id"])
    assert game.hero_names == {}


def test_event_history_pagination_and_time_cursor(client, game_data, monkeypatch):
    from goa2.domain.events import GameEvent, GameEventType
    from goa2.server.event_history import retain_events

    game = client.app.state.registry.get(game_data["game_id"])
    token = _token_for(game_data, "hero_arien")
    url = f"/games/{game.game_id}/events"
    assert client.get(url, headers=_auth(token)).json() == {
        "events": [],
        "last_event_id": 0,
        "last_event_time": 0,
        "has_more": False,
    }
    # Several events in the same clock tick must remain individually resumable.
    monkeypatch.setattr("goa2.server.event_history.time.time_ns", lambda: 1_000_000_000)
    events = [
        GameEvent(event_type=GameEventType.GOLD_GAINED, metadata={"amount": i}) for i in range(3)
    ]
    retain_events(game, events)
    retain_events(game, events)  # merged timer/action results do not duplicate events
    first = client.get(url, params={"limit": 2}, headers=_auth(token)).json()
    assert [e["event_id"] for e in first["events"]] == [1, 2]
    assert first["has_more"] is True
    assert first["last_event_id"] == 2
    assert first["last_event_time"] == 1001
    for key, cursor in [("after_event_id", 2), ("after_event_time", 1001)]:
        page = client.get(url, params={key: cursor}, headers=_auth(token)).json()
        assert [e["event_id"] for e in page["events"]] == [3]
        assert page["has_more"] is False
    empty = client.get(url, params={"after_event_id": 3}, headers=_auth(token)).json()
    assert empty["events"] == []
    assert empty["last_event_id"] == 3


@pytest.mark.parametrize(
    "params,status",
    [
        ({"after_event_id": -1}, 422),
        ({"after_event_time": -1}, 422),
        ({"limit": 0}, 422),
        ({"limit": 1001}, 422),
        ({"after_event_id": "bad"}, 422),
        ({"after_event_id": 0, "after_event_time": 0}, 400),
        ({"after_event_id": 1}, 400),
    ],
)
def test_event_history_validates_cursor(client, game_data, params, status):
    token = _token_for(game_data, "hero_arien")
    response = client.get(
        f"/games/{game_data['game_id']}/events", params=params, headers=_auth(token)
    )
    assert response.status_code == status


def test_event_history_auth(client, game_data):
    url = f"/games/{game_data['game_id']}/events"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=_auth("invalid")).status_code == 401
    token = _token_for(game_data, "hero_arien")
    assert client.get("/games/another-game/events", headers=_auth(token)).status_code == 403
    assert client.get(url, headers=_auth(game_data["spectator_token"])).status_code == 200


def test_event_history_freezes_viewpoint_at_emission(client, game_data):
    from goa2.domain.events import GameEvent, GameEventType
    from goa2.engine.session import SessionResult, SessionResultType
    from goa2.server.result_logging import log_session_result

    game = client.app.state.registry.get(game_data["game_id"])
    hero = game.session.state.get_hero("hero_arien")
    card = hero.hand[0]
    result = SessionResult(
        result_type=SessionResultType.ACTION_COMPLETE,
        current_phase=game.session.current_phase,
        events=[
            GameEvent(
                event_type=GameEventType.CARD_RETRIEVED,
                actor_id=hero.id,
                metadata={"card_id": card.id},
            )
        ],
    )
    game.game_logger = None  # retention must not depend on optional logging
    log_session_result(game, result)
    # A later public reveal must not change an earlier private event.
    hero.hand.remove(card)
    card.is_facedown = False
    hero.discard_pile.append(card)
    for viewer in ("hero_arien", "hero_wasp", "spectator"):
        token = (
            game_data["spectator_token"] if viewer == "spectator" else _token_for(game_data, viewer)
        )
        event = client.get(f"/games/{game.game_id}/events", headers=_auth(token)).json()["events"][
            0
        ]
        assert event["metadata"]["card_id"] == (card.id if viewer == "hero_arien" else None)
        assert event["event_id"] == 1


def test_rest_gold_events_survive_restart(client, game_data):
    from goa2.server.registry import GameRegistry

    registry = client.app.state.registry
    game = registry.get(game_data["game_id"])
    game.session.state.cheats_enabled = True
    token = _token_for(game_data, "hero_arien")
    emitted = []
    for amount in (2, 3):
        response = client.post(
            f"/games/{game.game_id}/cheats/gold",
            json={"hero_id": "hero_arien", "amount": amount},
            headers=_auth(token),
        )
        assert response.status_code == 200
        emitted.extend(response.json()["events"])
    restored = GameRegistry(save_dir=registry._save_dir)
    assert restored.restore_all() == 1
    client.app.state.registry = restored
    history = client.get(f"/games/{game.game_id}/events", headers=_auth(token)).json()
    assert history["events"] == emitted
    response = client.post(
        f"/games/{game.game_id}/cheats/gold",
        json={"hero_id": "hero_arien", "amount": 1},
        headers=_auth(token),
    )
    assert response.json()["events"][0]["event_id"] == 3


def test_rest_engine_events_are_retained(client, game_data):
    from goa2.domain.models import GamePhase
    from goa2.engine.handler import push_steps
    from goa2.engine.steps import PlaceUnitStep

    game = client.app.state.registry.get(game_data["game_id"])
    state = game.session.state
    state.phase = GamePhase.RESOLUTION
    destination = next(h for h in state.board.tiles if h not in state.entity_locations.values())
    push_steps(state, [PlaceUnitStep(unit_id="hero_arien", target_hex_arg=destination)])
    url = f"/games/{game_data['game_id']}"
    token = _token_for(game_data, "hero_arien")
    response = client.post(url + "/advance", headers=_auth(token))
    assert response.status_code == 200
    emitted = response.json()["events"]
    assert emitted
    recovered = client.get(url + "/events", headers=_auth(token)).json()
    assert [event["event_id"] for event in emitted] == list(range(1, len(emitted) + 1))
    assert recovered["events"] == emitted


def test_live_delivery_reuses_retained_visibility_after_later_changes(client, game_data):
    from goa2.domain.events import GameEvent, GameEventType
    from goa2.domain.views import _build_board_view
    from goa2.engine.session import SessionResult, SessionResultType
    from goa2.server.event_history import event_for_viewer, events_for_delivery, retain_events
    from goa2.server.routes_games import _result_to_response
    from goa2.server.ws import _capture_broadcast, _capture_player_update

    game = client.app.state.registry.get(game_data["game_id"])
    hero = game.session.state.get_hero("hero_arien")
    card = hero.hand[0]
    event = GameEvent(
        event_type=GameEventType.TIMER_EXPIRED, actor_id=hero.id, metadata={"card_id": card.id}
    )
    retain_events(game, [event])
    # The subsequent action reveals the selected card before this batch is sent.
    hero.hand.remove(card)
    card.is_facedown = False
    hero.discard_pile.append(card)
    game.ws_connections = {pt["token"]: object() for pt in game_data["player_tokens"]}
    game.spectator_ws_connections = {1: object()}
    messages = _capture_broadcast(game, [event.model_dump()])
    result = SessionResult(
        result_type=SessionResultType.ACTION_COMPLETE,
        current_phase=game.session.current_phase,
        events=[event],
    )
    for token, _, message in messages:
        hero_id = game.player_tokens[token] if token else None
        auth_token = token or game.spectator_token
        recovered = client.get(f"/games/{game.game_id}/events", headers=_auth(auth_token)).json()[
            "events"
        ]
        assert message["events"] == recovered
        assert message["events"][0]["metadata"]["card_id"] == (
            card.id if hero_id == hero.id else None
        )
        assert _result_to_response(result, game, hero_id).events == recovered
        if token:
            update = _capture_player_update(
                game, token, [event.model_dump()], board_view=_build_board_view(game.session.state)
            )
            assert update[2]["events"] == recovered
    # Delivery must not hand out references that can mutate the durable history.
    delivered = events_for_delivery([event.model_dump()], game, "hero_arien")
    delivered[0]["metadata"]["card_id"] = "changed"
    assert event_for_viewer(game.event_history[0], "hero_arien")["metadata"]["card_id"] == card.id


def test_public_history_events_store_one_payload_for_all_viewers(client, game_data):
    import json
    from pathlib import Path

    from goa2.domain.events import GameEvent, GameEventType
    from goa2.server.event_history import retain_events

    registry = client.app.state.registry
    game = registry.get(game_data["game_id"])
    event = GameEvent(
        event_type=GameEventType.GOLD_GAINED,
        actor_id="hero_arien",
        metadata={"amount": 2, "reason": "public-history-test"},
    )
    retain_events(game, [event])
    registry.save_game(game.game_id)
    saved = json.loads((Path(registry._save_dir) / f"{game.game_id}.json").read_text())
    entry = saved["event_history"][0]
    assert entry["payloads"] == [event.model_dump(mode="json")]
    assert entry["viewers"] == {}
    assert json.dumps(entry).count("public-history-test") == 1
    for token in [*game.hero_to_token.values(), game.spectator_token]:
        response = client.get(f"/games/{game.game_id}/events", headers=_auth(token))
        assert response.json()["events"] == [event.model_dump(mode="json")]


def test_history_compaction_shares_identical_private_variants():
    from goa2.domain.events import GameEvent, GameEventType
    from goa2.server.event_history import compact_history, event_for_viewer

    public = GameEvent(
        event_type=GameEventType.TIMER_EXPIRED,
        event_id=1,
        event_time=1000,
        metadata={"selection": None},
    ).model_dump(mode="json")
    private = {**public, "metadata": {"selection": "private_card"}}
    history = compact_history(
        [
            {
                "event_id": 1,
                "event_time": 1000,
                "viewers": {
                    "spectator": public,
                    "hero_a": private,
                    "hero_b": private.copy(),
                    "hero_c": public.copy(),
                },
            }
        ]
    )
    assert len(history[0]["payloads"]) == 2
    assert history[0]["viewers"] == {"hero_a": 1, "hero_b": 1}
    assert event_for_viewer(history[0], None) == public
    assert event_for_viewer(history[0], "hero_c") == public
    assert event_for_viewer(history[0], "hero_a") == private
    assert event_for_viewer(history[0], "hero_b") == private
    assert compact_history(history) == history


def test_legacy_history_migrates_without_rechecking_visibility(client, game_data):
    import json
    from pathlib import Path

    from goa2.domain.events import GameEvent, GameEventType
    from goa2.server.event_history import event_for_viewer, retain_events
    from goa2.server.registry import GameRegistry

    registry = client.app.state.registry
    game = registry.get(game_data["game_id"])
    hero = game.session.state.get_hero("hero_arien")
    card = hero.hand[0]
    retain_events(
        game,
        [
            GameEvent(
                event_type=GameEventType.GOLD_GAINED, actor_id=hero.id, metadata={"amount": 1}
            ),
            GameEvent(
                event_type=GameEventType.CARD_RETRIEVED,
                actor_id=hero.id,
                metadata={"card_id": card.id},
            ),
        ],
    )
    legacy = [
        {
            "event_id": entry["event_id"],
            "event_time": entry["event_time"],
            "viewers": {
                viewer: event_for_viewer(entry, None if viewer == "spectator" else viewer)
                for viewer in [*game.hero_to_token, "spectator"]
            },
        }
        for entry in game.event_history
    ]
    assert len(game.event_history[1]["payloads"]) == 2
    assert game.event_history[1]["viewers"] == {"hero_arien": 1}
    # Loading must preserve the earlier private payload despite today's reveal.
    hero.hand.remove(card)
    card.is_facedown = False
    hero.discard_pile.append(card)
    registry.save_game(game.game_id)
    save_path = Path(registry._save_dir) / f"{game.game_id}.json"
    saved = json.loads(save_path.read_text())
    saved["event_history"] = legacy
    save_path.write_text(json.dumps(saved))
    restored = GameRegistry(save_dir=registry._save_dir)
    assert restored.restore_all() == 1
    client.app.state.registry = restored
    restored_game = restored.get(game.game_id)
    assert [len(entry["payloads"]) for entry in restored_game.event_history] == [1, 2]
    for viewer in [*game.hero_to_token, "spectator"]:
        token = game.spectator_token if viewer == "spectator" else game.hero_to_token[viewer]
        response = client.get(f"/games/{game.game_id}/events", headers=_auth(token))
        assert response.json()["events"] == [entry["viewers"][viewer] for entry in legacy]
    next_event = GameEvent(event_type=GameEventType.GOLD_GAINED, metadata={"amount": 3})
    retain_events(restored_game, [next_event])
    assert next_event.event_id == 3
    restored.save_game(game.game_id)
    assert json.loads(save_path.read_text())["event_history"] == restored_game.event_history
