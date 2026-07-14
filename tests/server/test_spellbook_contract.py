from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from goa2.domain.models import CardState
from goa2.server.app import create_app


@pytest.fixture
def client(tmp_path):
    os.environ["GOA2_SAVE_DIR"] = str(tmp_path)
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    os.environ.pop("GOA2_SAVE_DIR", None)


@pytest.fixture
def game_data(client):
    response = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Gydion"],
            "blue_heroes": ["Arien"],
        },
    )
    assert response.status_code == 201
    return response.json()


def _token(game_data: dict, hero_id: str) -> str:
    return next(
        player["token"] for player in game_data["player_tokens"] if player["hero_id"] == hero_id
    )


def _hero(view: dict, hero_id: str) -> dict:
    return next(
        hero for team in view["teams"].values() for hero in team["heroes"] if hero["id"] == hero_id
    )


def _prepare_server_spellbook(client: TestClient, game_id: str) -> int:
    state = client.app.state.registry.get(game_id).session.state
    gydion = state.get_hero("hero_gydion")
    assert gydion is not None
    for spell in gydion.spells:
        spell.state = CardState.SPELLBOOK
        spell.is_facedown = True
    magic_missile = next(spell for spell in gydion.spells if spell.id == "magic_missile")
    magic_missile.state = CardState.OUTSIDE_SPELLBOOK
    magic_missile.is_facedown = False
    client.app.state.registry.save_game(game_id)
    return len(gydion.spellbook)


def test_rest_spellbook_views_preserve_owner_opponent_and_spectator_secrecy(
    client, game_data
) -> None:
    game_id = game_data["game_id"]
    prepared_count = _prepare_server_spellbook(client, game_id)
    tokens = [
        (_token(game_data, "hero_gydion"), True),
        (_token(game_data, "hero_arien"), False),
        (game_data["spectator_token"], False),
    ]

    for token, is_owner in tokens:
        response = client.get(
            f"/games/{game_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        gydion = _hero(response.json()["view"], "hero_gydion")
        if is_owner:
            assert len(gydion["spellbook"]) == prepared_count
        else:
            assert gydion["spellbook"] == {"count": prepared_count}
        assert [spell["id"] for spell in gydion["cast_spells"]] == ["magic_missile"]


def test_websocket_initial_state_uses_the_same_spellbook_visibility(client, game_data) -> None:
    game_id = game_data["game_id"]
    prepared_count = _prepare_server_spellbook(client, game_id)

    for token, is_owner in [
        (_token(game_data, "hero_gydion"), True),
        (game_data["spectator_token"], False),
    ]:
        with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as websocket:
            message = websocket.receive_json()
        assert message["type"] == "STATE_UPDATE"
        gydion = _hero(message["view"], "hero_gydion")
        if is_owner:
            assert len(gydion["spellbook"]) == prepared_count
        else:
            assert gydion["spellbook"] == {"count": prepared_count}
        assert [spell["id"] for spell in gydion["cast_spells"]] == ["magic_missile"]
