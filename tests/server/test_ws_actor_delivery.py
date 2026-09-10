"""Actor-first WebSocket delivery and snapshot-ordering regressions."""

import asyncio
import os
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from goa2.domain import views as views_module
from goa2.server import ws as ws_module
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


def test_actor_update_is_sent_before_other_views_are_built(client, game_data, monkeypatch):
    game_id = game_data["game_id"]
    arien_token = _token_for(game_data, "hero_arien")
    wasp_token = _token_for(game_data, "hero_wasp")
    game = client.app.state.registry.get(game_id)

    trace: list[str] = []
    lock_waiter = None
    measuring = False
    clock = [0.0]
    timing_record: dict = {}
    real_build = ws_module._build_state_update
    real_send = ws_module._send_captured_broadcast

    def traced_build(game, hero_id, **kwargs):
        if measuring and hero_id == "hero_wasp":
            clock[0] += 0.2
        trace.append(f"build:{hero_id}")
        return real_build(game, hero_id, **kwargs)

    async def traced_send(game, messages):
        nonlocal lock_waiter
        tokens = [token for token, _, _ in messages]
        if tokens == [arien_token]:
            assert game.lock.locked(), "the actor send must keep the state snapshot stable"
            trace.append("send:actor")
            clock[0] += 0.01

            async def wait_for_snapshot_release():
                async with game.lock:
                    trace.append("next-mutation")

            lock_waiter = asyncio.create_task(wait_for_snapshot_release())
            await asyncio.sleep(0)
            assert not lock_waiter.done()
        elif messages:
            assert not game.lock.locked(), "remaining network sends should release the state lock"
            trace.append("send:remaining")
            clock[0] += 0.02
            assert lock_waiter is not None
            await asyncio.wait_for(lock_waiter, timeout=1)
        await real_send(game, messages)

    def capture_timing(_action, **kwargs):
        timing_record.update(kwargs)

    monkeypatch.setattr(ws_module, "_build_state_update", traced_build)
    monkeypatch.setattr(ws_module, "_send_captured_broadcast", traced_send)
    monkeypatch.setattr(
        ws_module,
        "time",
        SimpleNamespace(perf_counter=lambda: clock[0], monotonic=time.monotonic),
    )
    monkeypatch.setattr(game.game_logger, "log_timing", capture_timing)

    with (
        client.websocket_connect(f"/games/{game_id}/ws?token={arien_token}") as actor_ws,
        client.websocket_connect(f"/games/{game_id}/ws?token={wasp_token}") as opponent_ws,
    ):
        actor_view = actor_ws.receive_json()["view"]
        opponent_ws.receive_json()
        trace.clear()
        arien = next(
            hero
            for team in actor_view["teams"].values()
            for hero in team["heroes"]
            if hero["id"] == "hero_arien"
        )

        measuring = True
        actor_ws.send_json(
            {
                "type": "COMMIT_CARD",
                "card_id": arien["hand"][0]["id"],
                "client_action_id": "actor-only-id",
            }
        )
        assert actor_ws.receive_json()["type"] == "ACTION_RESULT"
        actor_update = actor_ws.receive_json()
        opponent_update = opponent_ws.receive_json()

    assert trace.index("build:hero_arien") < trace.index("send:actor")
    assert trace.index("send:actor") < trace.index("build:hero_wasp")
    assert trace.index("build:hero_wasp") < trace.index("send:remaining")
    assert trace.index("build:hero_wasp") < trace.index("next-mutation")
    assert actor_update["client_action_id"] == "actor-only-id"
    assert "client_action_id" not in opponent_update
    assert timing_record["send_ms"] == pytest.approx(30.0)
    assert timing_record["fanout_ms"] == pytest.approx(200.0)


def test_split_capture_uses_one_board_and_does_not_duplicate_actor(client, game_data, monkeypatch):
    game = client.app.state.registry.get(game_data["game_id"])
    arien_token = _token_for(game_data, "hero_arien")
    wasp_token = _token_for(game_data, "hero_wasp")
    game.ws_connections = {wasp_token: object(), arien_token: object()}

    calls = 0
    real_builder = views_module._build_board_view

    def counted_builder(state):
        nonlocal calls
        calls += 1
        return real_builder(state)

    monkeypatch.setattr(ws_module, "_build_board_view", counted_builder)

    board_view = ws_module._build_board_view(game.session.state)
    actor_message = ws_module._capture_player_update(
        game,
        arien_token,
        board_view=board_view,
        client_action_id="actor-private",
    )
    remaining = ws_module._capture_broadcast(
        game,
        board_view=board_view,
        exclude_token=arien_token,
    )

    assert calls == 1
    assert actor_message is not None
    assert actor_message[0] == arien_token
    assert actor_message[2]["client_action_id"] == "actor-private"
    assert [token for token, _, _ in remaining] == [wasp_token]
    assert all("client_action_id" not in message for _, _, message in remaining)
    assert actor_message[2]["view"]["board"] is remaining[0][2]["view"]["board"]
