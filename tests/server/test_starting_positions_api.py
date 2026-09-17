import os

import jsonpatch
import pytest
from fastapi.testclient import TestClient

from goa2.domain.types import HeroID
from goa2.server.app import create_app
from goa2.server.replay import ReplayCursor, load_replay, replay_game, state_body
from goa2.server.share_bake import bake_replay_share


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def create(client):
    result = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Min", "Arien"],
            "blue_heroes": ["Wasp", "Razzle"],
        },
    )
    assert result.status_code == 201
    data = result.json()
    tokens = {p["hero_id"]: p["token"] for p in data["player_tokens"]}
    return data, tokens, client.app.state.registry.get(data["game_id"])


def send(client, data, token, action, expected="STARTING_POSITION_UPDATED"):
    with client.websocket_connect(f"/games/{data['game_id']}/ws?token={token}") as ws:
        assert ws.receive_json()["type"] == "STATE_UPDATE"
        ws.send_json({"type": "STARTING_POSITION", **action})
        reply = ws.receive_json()
        assert reply["type"] == expected, reply
        if expected != "ERROR":
            update = ws.receive_json()
            assert update["type"] == "STATE_UPDATE"
            return update["view"]


def test_live_moves_swaps_seek_rewind_and_baked_share(client):
    data, tokens, game = create(client)
    initial = dict(game.session.state.entity_locations)
    from goa2.engine.starting_positions import destinations

    dest = destinations(game.session.state, "hero_min")[0]
    send(
        client,
        data,
        tokens["hero_min"],
        {"op": "move", "destination": dest.model_dump(), "hero_id": "hero_wasp"},
    )
    moved = dict(game.session.state.entity_locations)
    assert moved["hero_min"] == dest and moved["hero_wasp"] == initial["hero_wasp"]
    view = send(client, data, tokens["hero_min"], {"op": "request_swap", "target": "hero_arien"})
    request = view["starting_position"]["requests"][0]["id"]
    setup, decisions = load_replay(game.replay_recorder.path)
    assert len(decisions) == 1  # requests are not board decisions
    send(
        client,
        data,
        tokens["hero_wasp"],
        {"op": "respond_swap", "request_id": request, "accept": True},
        "ERROR",
    )
    send(
        client,
        data,
        tokens["hero_arien"],
        {"op": "respond_swap", "request_id": request, "accept": True},
    )
    swapped = dict(game.session.state.entity_locations)
    assert swapped["hero_min"] == initial["hero_arien"]
    assert swapped["hero_arien"] == dest
    setup, decisions = load_replay(game.replay_recorder.path)
    assert [d["type"] for d in decisions] == ["starting_position", "starting_position"]
    cursor = ReplayCursor(setup, decisions)
    for index, positions in [(2, swapped), (0, initial), (1, moved), (2, swapped)]:
        state = cursor.seek(index).state
        assert state.entity_locations == positions
        assert state.last_turn_positions == positions
    assert replay_game(game.replay_recorder.path).state.entity_locations == swapped
    rewind = {"type": "ov_rewind", "hero": "hero_min", "r": 1, "t": 1, "to": 1}
    assert ReplayCursor(setup, [*decisions, rewind]).seek(3).state.entity_locations == moved
    # Finish through an existing replayable override, then run the real share
    # baker and compare its public compressed frames to regular reconstruction.
    game.replay_recorder.record_override(
        {
            "type": "ov_patch",
            "hero": "hero_min",
            "r": 1,
            "t": 1,
            "op": "set_life_counters",
            "args": {"team": "BLUE", "value": 0},
            "voters": list(tokens),
        }
    )
    result = bake_replay_share(
        game.replay_recorder.path, data["game_id"], os.environ["GOA2_SHARE_DIR"]
    )
    assert result["ok"], result
    setup, decisions = load_replay(game.replay_recorder.path)
    meta = client.get(f"/shared/{result['token']}").json()
    assert meta["decisions"][0]["sel"] == {"destination": dest.model_dump()}
    assert meta["decisions"][1]["sel"] == {"swap_with": "hero_arien"}
    cursor = ReplayCursor(setup, decisions)
    for index in range(len(decisions) + 1):
        response = client.get(f"/shared/{result['token']}/state?decision={index}")
        assert response.status_code == 200, response.text
        group = response.json()
        body = group["keyframe"]
        for patch in group["patches"][: index - group["start"]]:
            body = jsonpatch.JsonPatch(patch).apply(body)
        assert body == state_body(cursor.seek(index), cursor_index=index, total=len(decisions))


def test_rejected_actions_are_not_recorded_and_commit_closes_window_until_uncommit(client):
    data, tokens, game = create(client)
    before = dict(game.session.state.entity_locations)
    send(
        client,
        data,
        data["spectator_token"],
        {"op": "move", "destination": {"q": 0, "r": 0, "s": 0}},
        "ERROR",
    )
    send(
        client,
        data,
        tokens["hero_min"],
        {"op": "move", "destination": {"q": 999, "r": -999, "s": 0}},
        "ERROR",
    )
    send(client, data, tokens["hero_min"], {"op": "request_swap", "target": "hero_wasp"}, "ERROR")
    assert load_replay(game.replay_recorder.path)[1] == []
    hero = game.session.state.get_hero(HeroID("hero_min"))
    with client.websocket_connect(f"/games/{data['game_id']}/ws?token={tokens['hero_min']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "COMMIT_CARD", "card_id": hero.hand[0].id})
        assert ws.receive_json()["type"] == "ACTION_RESULT"
        assert ws.receive_json()["view"]["starting_position"] is None
    send(client, data, tokens["hero_min"], {"op": "request_swap", "target": "hero_arien"}, "ERROR")
    assert game.session.state.entity_locations == before
    assert [d["type"] for d in load_replay(game.replay_recorder.path)[1]] == ["commit"]
    with client.websocket_connect(f"/games/{data['game_id']}/ws?token={tokens['hero_min']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "UNCOMMIT_CARD"})
        assert ws.receive_json()["type"] == "ACTION_RESULT"
        assert ws.receive_json()["view"]["starting_position"] is not None
    from goa2.engine.starting_positions import destinations

    dest = destinations(game.session.state, "hero_min")[0]
    send(client, data, tokens["hero_min"], {"op": "move", "destination": dest.model_dump()})
    setup, decisions = load_replay(game.replay_recorder.path)
    assert [d["type"] for d in decisions] == ["commit", "uncommit", "starting_position"]
    replayed = replay_game(game.replay_recorder.path).state
    assert replayed.entity_locations == game.session.state.entity_locations
    assert replayed.last_turn_positions == game.session.state.last_turn_positions
    assert ReplayCursor(setup, decisions).seek(2).state.entity_locations == before


def test_legacy_replay_without_adjustments_keeps_original_placement(client):
    _, _, game = create(client)
    replayed = replay_game(game.replay_recorder.path)
    assert replayed.state.entity_locations == game.session.state.entity_locations
    assert replayed.state.last_turn_positions == game.session.state.last_turn_positions
