import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from goa2.server.app import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def _create(client):
    r = client.post("/drafts", json={"host_name": "Alice", "red_size": 2, "blue_size": 2})
    assert r.status_code == 201
    return r.json()


def test_connect_receives_initial_state(client):
    d = _create(client)
    url = f"/drafts/{d['draft_id']}/ws?token={d['player_token']}"
    with client.websocket_connect(url) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "STATE_UPDATE"
        assert msg["draft"]["status"] == "LOBBY"
        assert msg["you"]["id"] == "p1"


def test_rest_mutation_pushes_update_to_socket(client):
    d = _create(client)
    url = f"/drafts/{d['draft_id']}/ws?token={d['player_token']}"
    with client.websocket_connect(url) as ws:
        ws.receive_json()  # initial state
        # A second player joins via REST; the open socket should be pushed an update.
        jr = client.post(f"/drafts/{d['draft_id']}/join", json={"display_name": "Bob"})
        assert jr.status_code == 200
        pushed = ws.receive_json()
        assert pushed["type"] == "STATE_UPDATE"
        assert [p["id"] for p in pushed["draft"]["players"]] == ["p1", "p2"]


def test_get_view_refreshes(client):
    d = _create(client)
    url = f"/drafts/{d['draft_id']}/ws?token={d['player_token']}"
    with client.websocket_connect(url) as ws:
        ws.receive_json()  # initial
        ws.send_json({"type": "GET_VIEW"})
        msg = ws.receive_json()
        assert msg["type"] == "STATE_UPDATE"


def test_non_getview_message_is_rejected(client):
    d = _create(client)
    url = f"/drafts/{d['draft_id']}/ws?token={d['player_token']}"
    with client.websocket_connect(url) as ws:
        ws.receive_json()  # initial
        ws.send_json({"type": "JOIN"})
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"


def test_invalid_token_closes(client):
    d = _create(client)
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/drafts/{d['draft_id']}/ws?token=bogus") as ws,
    ):
        ws.receive_json()


def test_spectator_receives_public_state_without_you(client):
    d = _create(client)
    url = f"/drafts/{d['draft_id']}/ws?token={d['spectator_token']}"
    with client.websocket_connect(url) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "STATE_UPDATE"
        assert msg["you"] is None
        assert msg["draft"]["status"] == "LOBBY"
