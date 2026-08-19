"""A dead worker pool must degrade to a rejected override, not drop the player."""

import os
from concurrent.futures.process import BrokenProcessPool

import pytest
from fastapi.testclient import TestClient

from goa2.server import ws as ws_module
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


def _drain_until(ws, msg_type: str, limit: int = 12):
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == msg_type:
            return msg
    raise AssertionError(f"never saw {msg_type}")


def test_broken_pool_rejects_the_rewind_and_keeps_the_socket(client, game_data, monkeypatch):
    async def _explode(*_args, **_kwargs):
        raise BrokenProcessPool("worker died")

    monkeypatch.setattr(ws_module, "run_heavy", _explode)

    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        ws_a.send_json({"type": "PROPOSE_OVERRIDE", "family": "rewind", "to": 0})
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})

        resolved = _drain_until(ws_w, "OVERRIDE_RESOLVED")
        assert resolved["outcome"] == "rejected"

        # The socket must still be usable — a dropped connection is the bug.
        ws_a.send_json({"type": "GET_VIEW"})
        assert _drain_until(ws_a, "STATE_UPDATE")["view"]["phase"] == "PLANNING"
