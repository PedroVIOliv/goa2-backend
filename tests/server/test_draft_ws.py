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
    r = client.post("/drafts", json={"host_name": "Alice"})
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


def test_old_same_token_disconnect_does_not_unregister_replacement(client):
    d = _create(client)
    token = d["player_token"]
    url = f"/drafts/{d['draft_id']}/ws?token={token}"
    first_context = client.websocket_connect(url)
    first = first_context.__enter__()
    second_context = client.websocket_connect(url)
    second = second_context.__enter__()
    first_closed = False
    try:
        first.receive_json()
        second.receive_json()
        first_context.__exit__(None, None, None)
        first_closed = True

        managed = client.app.state.draft_registry.get(d["draft_id"])
        assert token in managed.ws_connections
        second.send_json({"type": "GET_VIEW"})
        assert second.receive_json()["type"] == "STATE_UPDATE"
    finally:
        if not first_closed:
            first_context.__exit__(None, None, None)
        second_context.__exit__(None, None, None)


def test_broadcast_allows_connections_to_change_during_send(client):
    import asyncio

    from goa2.server.draft_ws import broadcast_draft

    d = _create(client)
    managed = client.app.state.draft_registry.get(d["draft_id"])

    class MutatingSocket:
        async def send_json(self, _data):
            managed.ws_connections["new-token"] = object()

    managed.ws_connections = {d["player_token"]: MutatingSocket()}
    asyncio.run(broadcast_draft(managed, client.app.state.draft_registry))
    assert "new-token" in managed.ws_connections


def test_failed_broadcast_does_not_remove_reconnected_socket(client):
    import asyncio

    from goa2.server.draft_ws import broadcast_draft

    d = _create(client)
    token = d["player_token"]
    managed = client.app.state.draft_registry.get(d["draft_id"])
    replacement = object()

    class ReplacedSocket:
        async def send_json(self, _data):
            managed.ws_connections[token] = replacement
            raise RuntimeError("connection closed")

    managed.ws_connections = {token: ReplacedSocket()}
    asyncio.run(broadcast_draft(managed, client.app.state.draft_registry))
    assert managed.ws_connections[token] is replacement
