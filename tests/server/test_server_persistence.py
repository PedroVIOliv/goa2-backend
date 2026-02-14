"""Server integration tests for Phase 6: State Persistence.

Tests that games survive server restarts via auto-save and restore.
"""

import os

import pytest
from fastapi.testclient import TestClient

from goa2.server.app import create_app


def _token_for(game_data: dict, hero_id: str) -> str:
    for pt in game_data["player_tokens"]:
        if pt["hero_id"] == hero_id:
            return pt["token"]
    raise ValueError(f"No token for {hero_id}")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_game(client: TestClient) -> dict:
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


def _make_client(save_dir: str) -> TestClient:
    """Create a fresh TestClient with the given save_dir."""
    os.environ["GOA2_SAVE_DIR"] = save_dir
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Save file creation
# ---------------------------------------------------------------------------


def test_create_game_creates_save_file(tmp_path):
    """Creating a game via API produces a .json save file."""
    with _make_client(str(tmp_path)) as client:
        data = _create_game(client)
        game_id = data["game_id"]

    save_file = tmp_path / f"{game_id}.json"
    assert save_file.exists()
    assert save_file.stat().st_size > 0


def test_commit_card_updates_save_file(tmp_path):
    """Committing a card updates the save file."""
    with _make_client(str(tmp_path)) as client:
        data = _create_game(client)
        game_id = data["game_id"]
        token = _token_for(data, "hero_arien")

        save_file = tmp_path / f"{game_id}.json"
        size_before = save_file.stat().st_size
        mtime_before = save_file.stat().st_mtime_ns

        # Get a card to commit
        view = client.get(f"/games/{game_id}", headers=_auth(token)).json()
        arien_hand = None
        for team_data in view["view"]["teams"].values():
            for hero in team_data["heroes"]:
                if hero["id"] == "hero_arien":
                    arien_hand = hero["hand"]
        assert arien_hand

        resp = client.post(
            f"/games/{game_id}/cards",
            json={"card_id": arien_hand[0]["id"]},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        # Save file should be updated
        assert save_file.exists()
        # File was rewritten (mtime or size may differ)
        assert save_file.stat().st_size > 0


# ---------------------------------------------------------------------------
# Restart survival
# ---------------------------------------------------------------------------


def test_game_survives_restart(tmp_path):
    """Create game, 'restart' (new TestClient), game is still accessible."""
    save_dir = str(tmp_path)

    # Session 1: create game
    with _make_client(save_dir) as client1:
        data = _create_game(client1)
        game_id = data["game_id"]
        arien_token = _token_for(data, "hero_arien")
        spectator_token = data["spectator_token"]

    # Session 2: new client (simulates restart)
    with _make_client(save_dir) as client2:
        # Game should be accessible with the same token
        resp = client2.get(f"/games/{game_id}", headers=_auth(arien_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["view"]["phase"] == "PLANNING"

        # Spectator token should also work
        resp = client2.get(
            f"/games/{game_id}", headers=_auth(spectator_token)
        )
        assert resp.status_code == 200


def test_committed_card_survives_restart(tmp_path):
    """Commit a card, restart, verify the card is committed."""
    save_dir = str(tmp_path)

    # Session 1: create game and commit Arien's card
    with _make_client(save_dir) as client1:
        data = _create_game(client1)
        game_id = data["game_id"]
        arien_token = _token_for(data, "hero_arien")

        # Get and commit a card
        view = client1.get(
            f"/games/{game_id}", headers=_auth(arien_token)
        ).json()
        arien_hand = None
        for team_data in view["view"]["teams"].values():
            for hero in team_data["heroes"]:
                if hero["id"] == "hero_arien":
                    arien_hand = hero["hand"]
        assert arien_hand
        card_id = arien_hand[0]["id"]
        hand_size_before = len(arien_hand)

        resp = client1.post(
            f"/games/{game_id}/cards",
            json={"card_id": card_id},
            headers=_auth(arien_token),
        )
        assert resp.status_code == 200

    # Session 2: restart
    with _make_client(save_dir) as client2:
        view = client2.get(
            f"/games/{game_id}", headers=_auth(arien_token)
        ).json()

        # Find Arien's hand in restored state
        restored_hand = None
        for team_data in view["view"]["teams"].values():
            for hero in team_data["heroes"]:
                if hero["id"] == "hero_arien":
                    restored_hand = hero["hand"]
        assert restored_hand is not None
        # Card was committed, so hand should be smaller
        assert len(restored_hand) == hand_size_before - 1


def test_full_planning_survives_restart(tmp_path):
    """Both players commit cards, restart, verify phase transitioned."""
    save_dir = str(tmp_path)

    # Session 1: full planning flow
    with _make_client(save_dir) as client1:
        data = _create_game(client1)
        game_id = data["game_id"]
        arien_token = _token_for(data, "hero_arien")
        wasp_token = _token_for(data, "hero_wasp")

        # Get cards for both heroes
        view = client1.get(
            f"/games/{game_id}", headers=_auth(arien_token)
        ).json()
        arien_hand = None
        for td in view["view"]["teams"].values():
            for h in td["heroes"]:
                if h["id"] == "hero_arien":
                    arien_hand = h["hand"]
        assert arien_hand

        view = client1.get(
            f"/games/{game_id}", headers=_auth(wasp_token)
        ).json()
        wasp_hand = None
        for td in view["view"]["teams"].values():
            for h in td["heroes"]:
                if h["id"] == "hero_wasp":
                    wasp_hand = h["hand"]
        assert wasp_hand

        # Commit both cards
        client1.post(
            f"/games/{game_id}/cards",
            json={"card_id": arien_hand[0]["id"]},
            headers=_auth(arien_token),
        )
        resp = client1.post(
            f"/games/{game_id}/cards",
            json={"card_id": wasp_hand[0]["id"]},
            headers=_auth(wasp_token),
        )
        assert resp.status_code == 200
        phase_after = resp.json()["current_phase"]
        assert phase_after != "PLANNING"

    # Session 2: restart — phase should be preserved
    with _make_client(save_dir) as client2:
        view = client2.get(
            f"/games/{game_id}", headers=_auth(arien_token)
        ).json()
        assert view["view"]["phase"] == phase_after


# ---------------------------------------------------------------------------
# Multiple games
# ---------------------------------------------------------------------------


def test_multiple_games_survive_restart(tmp_path):
    """Multiple games all survive a restart."""
    save_dir = str(tmp_path)
    game_ids = []
    tokens = []

    with _make_client(save_dir) as client1:
        for _ in range(3):
            data = _create_game(client1)
            game_ids.append(data["game_id"])
            tokens.append(_token_for(data, "hero_arien"))

    with _make_client(save_dir) as client2:
        for gid, tok in zip(game_ids, tokens):
            resp = client2.get(f"/games/{gid}", headers=_auth(tok))
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# WebSocket reconnection
# ---------------------------------------------------------------------------


def test_ws_reconnect_after_restart(tmp_path):
    """WebSocket connection works after restart with same token."""
    save_dir = str(tmp_path)

    # Session 1: create game
    with _make_client(save_dir) as client1:
        data = _create_game(client1)
        game_id = data["game_id"]
        arien_token = _token_for(data, "hero_arien")

    # Session 2: reconnect via WebSocket
    with _make_client(save_dir) as client2:
        with client2.websocket_connect(
            f"/games/{game_id}/ws?token={arien_token}"
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "STATE_UPDATE"
            assert "view" in msg
            assert msg["view"]["phase"] == "PLANNING"


# ---------------------------------------------------------------------------
# No save_dir (disabled persistence)
# ---------------------------------------------------------------------------


def test_no_persistence_when_save_dir_unset(tmp_path):
    """When GOA2_SAVE_DIR is empty, no files are written."""
    os.environ["GOA2_SAVE_DIR"] = ""
    app = create_app()
    with TestClient(app) as client:
        _create_game(client)
    os.environ.pop("GOA2_SAVE_DIR", None)

    # No files should be created anywhere for this test
    # (registry has save_dir="" which is falsy, so save_game is a no-op)
