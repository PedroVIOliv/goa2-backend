"""Per-mutation timing instrumentation on the WebSocket path."""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from goa2.domain import views as views_module
from goa2.server import ws as ws_module
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
    gl.log_timing(
        "SUBMIT_INPUT",
        engine_ms=17.5,
        fanout_ms=31.2,
        send_ms=2.0,
        clients=4,
        lock_wait_ms=0.8,
        board_ms=4.2,
        recipient_views_ms=27.0,
        actor_update_ms=44.1,
        action_id="browser-7",
    )

    event = next(e for e in gl.events if e["type"] == "TIMING")
    assert event["data"] == {
        "action": "SUBMIT_INPUT",
        "engine_ms": 17.5,
        "fanout_ms": 31.2,
        "send_ms": 2.0,
        "total_ms": 50.7,
        "clients": 4,
        "lock_wait_ms": 0.8,
        "board_ms": 4.2,
        "recipient_views_ms": 27.0,
        "actor_update_ms": 44.1,
        "action_id": "browser-7",
    }

    text = (tmp_path / "g1.log").read_text()
    assert "TIMING: SUBMIT_INPUT" in text
    assert "engine=17.5ms" in text
    assert "clients=4" in text
    assert "lock_wait=0.8ms" in text
    assert "actor_update=44.1ms" in text


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
        ws.send_json(
            {
                "type": "COMMIT_CARD",
                "card_id": arien["hand"][0]["id"],
                "client_action_id": "browser-commit-1",
            }
        )
        action_result = ws.receive_json()
        state_update = ws.receive_json()
        assert action_result["type"] == "ACTION_RESULT"
        assert action_result["client_action_id"] == "browser-commit-1"
        assert state_update["type"] == "STATE_UPDATE"
        assert state_update["client_action_id"] == "browser-commit-1"

    lines = _timing_events(log_dir, game_id)
    assert lines, "a mutation must record a TIMING line"
    assert "COMMIT_CARD" in lines[-1]
    assert "clients=1" in lines[-1]
    assert "action_id=browser-commit-1" in lines[-1]


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


def test_capture_builds_one_shared_public_board(client, game_data, monkeypatch):
    game = client.app.state.registry.get(game_data["game_id"])
    arien_token = _token_for(game_data, "hero_arien")
    wasp_token = _token_for(game_data, "hero_wasp")
    game.ws_connections = {arien_token: object(), wasp_token: object()}

    calls = 0
    real_builder = views_module._build_board_view

    def counted_builder(state):
        nonlocal calls
        calls += 1
        return real_builder(state)

    monkeypatch.setattr(ws_module, "_build_board_view", counted_builder)

    messages = ws_module._capture_broadcast(game)

    assert calls == 1
    assert messages[0][2]["view"]["board"] is messages[1][2]["view"]["board"]


def test_capture_skips_board_work_without_recipients(client, game_data, monkeypatch):
    game = client.app.state.registry.get(game_data["game_id"])
    monkeypatch.setattr(
        ws_module,
        "_build_board_view",
        lambda _state: pytest.fail("no recipient needs a board view"),
    )

    timing: dict[str, float] = {}
    assert ws_module._capture_broadcast(game, timing=timing) == []
    assert timing == {"board_ms": 0.0, "recipient_views_ms": 0.0}


def test_capture_prioritizes_the_acting_player(client, game_data):
    game = client.app.state.registry.get(game_data["game_id"])
    arien_token = _token_for(game_data, "hero_arien")
    wasp_token = _token_for(game_data, "hero_wasp")
    # Put the actor second to prove priority doesn't depend on connection order.
    game.ws_connections = {wasp_token: object(), arien_token: object()}

    messages = ws_module._capture_broadcast(
        game,
        priority_token=arien_token,
        client_action_id="private-correlation-id",
    )

    assert [token for token, _, _ in messages] == [arien_token, wasp_token]
    assert messages[0][2]["client_action_id"] == "private-correlation-id"
    assert "client_action_id" not in messages[1][2]


def test_capture_reuses_only_the_spectator_scoped_payload(client, game_data, monkeypatch):
    from goa2.domain.events import GameEvent, GameEventType
    from goa2.domain.models import TokenType

    game = client.app.state.registry.get(game_data["game_id"])
    arien_token = _token_for(game_data, "hero_arien")
    wasp_token = _token_for(game_data, "hero_wasp")
    game.ws_connections = {arien_token: object(), wasp_token: object()}
    game.spectator_ws_connections = {1: object(), 2: object()}

    state = game.session.state
    mine = state.token_pool[TokenType.MINE_BLAST][0]
    mine.owner_id = "hero_arien"
    destination = next(hex_ for hex_, tile in state.board.tiles.items() if not tile.is_occupied)
    state.place_entity(mine.id, destination)
    events = [
        GameEvent(
            event_type=GameEventType.TOKEN_PLACED,
            actor_id="hero_arien",
            target_id=mine.id,
            metadata={"token_type": TokenType.MINE_BLAST.value},
        ).model_dump()
    ]

    event_viewers: list[str | None] = []
    real_events_for_viewer = ws_module.events_for_viewer

    def counted_events_for_viewer(_events, _state, hero_id):
        event_viewers.append(hero_id)
        return real_events_for_viewer(_events, _state, hero_id)

    monkeypatch.setattr(ws_module, "events_for_viewer", counted_events_for_viewer)

    messages = ws_module._capture_broadcast(
        game,
        events,
        priority_token=arien_token,
        client_action_id="actor-private-id",
    )

    player_payloads = [payload for token, _, payload in messages if token is not None]
    spectator_payloads = [payload for token, _, payload in messages if token is None]

    assert event_viewers == ["hero_arien", "hero_wasp", None]
    assert player_payloads[0] is not player_payloads[1]
    assert spectator_payloads[0] is spectator_payloads[1]
    assert player_payloads[0]["events"][0]["metadata"]["token_type"] == "mine_blast"
    assert player_payloads[1]["events"][0]["metadata"]["token_type"] == "mine"
    assert spectator_payloads[0]["events"][0]["metadata"]["token_type"] == "mine"
    assert "client_action_id" not in spectator_payloads[0]
    assert player_payloads[0]["client_action_id"] == "actor-private-id"


def test_send_serializes_a_shared_payload_once(monkeypatch):
    send_order = []

    class RecordingSocket:
        def __init__(self, name):
            self.name = name
            self.json_messages = []
            self.text_messages = []

        async def send_json(self, data):
            send_order.append(self.name)
            self.json_messages.append(data)

        async def send_text(self, data):
            send_order.append(self.name)
            self.text_messages.append(data)

    class Game:
        def __init__(self):
            self.spectator_ws_connections = {}
            self.ws_connections = {}

    first = RecordingSocket("spectator-one")
    second = RecordingSocket("spectator-two")
    player = RecordingSocket("player")
    shared_spectator_payload = {"type": "STATE_UPDATE", "view": {"public": "same"}}
    player_payload = {"type": "STATE_UPDATE", "view": {"hand": "private"}}
    messages = [
        ("player-token", player, player_payload),
        (None, first, shared_spectator_payload),
        (None, second, shared_spectator_payload),
    ]

    real_dumps = ws_module.json.dumps
    encoded_payloads = []

    def counted_dumps(data, **kwargs):
        send_order.append("encode")
        encoded_payloads.append(data)
        return real_dumps(data, **kwargs)

    monkeypatch.setattr(ws_module.json, "dumps", counted_dumps)

    asyncio.run(ws_module._send_captured_broadcast(Game(), messages))

    assert encoded_payloads == [shared_spectator_payload]
    expected = real_dumps(shared_spectator_payload, separators=(",", ":"), ensure_ascii=False)
    assert first.text_messages == [expected]
    assert second.text_messages == [expected]
    assert player.json_messages == [player_payload]
    assert send_order == ["player", "encode", "spectator-one", "spectator-two"]


def test_failed_shared_send_keeps_replacement_and_continues():
    class Game:
        def __init__(self):
            self.spectator_ws_connections = {}
            self.ws_connections = {}

    class RecordingSocket:
        def __init__(self):
            self.text_messages = []

        async def send_text(self, data):
            self.text_messages.append(data)

    class ReplacingFailSocket:
        async def send_text(self, _data):
            game.spectator_ws_connections[id(self)] = replacement
            raise RuntimeError("disconnected")

    game = Game()
    failed = ReplacingFailSocket()
    replacement = RecordingSocket()
    survivor = RecordingSocket()
    game.spectator_ws_connections = {id(failed): failed, id(survivor): survivor}
    shared_payload = {"type": "STATE_UPDATE", "view": {"public": "same"}}

    asyncio.run(
        ws_module._send_captured_broadcast(
            game,
            [(None, failed, shared_payload), (None, survivor, shared_payload)],
        )
    )

    assert game.spectator_ws_connections[id(failed)] is replacement
    assert game.spectator_ws_connections[id(survivor)] is survivor
    assert survivor.text_messages


def test_shared_encoding_failure_does_not_abort_later_payloads(monkeypatch):
    class RecordingSocket:
        def __init__(self):
            self.json_messages = []

        async def send_json(self, data):
            self.json_messages.append(data)

    class Game:
        def __init__(self):
            self.spectator_ws_connections = {}
            self.ws_connections = {}

    game = Game()
    first = RecordingSocket()
    second = RecordingSocket()
    player = RecordingSocket()
    shared_payload = {"type": "STATE_UPDATE"}
    player_payload = {"type": "STATE_UPDATE", "view": {"hand": "private"}}
    game.spectator_ws_connections = {id(first): first, id(second): second}
    game.ws_connections = {"player-token": player}
    real_dumps = ws_module.json.dumps

    def fail_shared_payload(data, **kwargs):
        if data is shared_payload:
            raise TypeError("not serializable")
        return real_dumps(data, **kwargs)

    monkeypatch.setattr(ws_module.json, "dumps", fail_shared_payload)

    asyncio.run(
        ws_module._send_captured_broadcast(
            game,
            [
                (None, first, shared_payload),
                (None, second, shared_payload),
                ("player-token", player, player_payload),
            ],
        )
    )

    assert game.spectator_ws_connections == {}
    assert game.ws_connections["player-token"] is player
    assert player.json_messages == [player_payload]
