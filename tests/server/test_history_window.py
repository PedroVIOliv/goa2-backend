"""Player replay windows are independent of retained history and spectators."""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goa2.domain.models import GamePhase
from goa2.domain.models.enums import HistoryScope
from goa2.server import history_backfill, live_history, routes_history
from goa2.server.app import create_app
from goa2.server.registry import GameRegistry


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def create(client, scope=None, hero="Arien"):
    body = {"red_heroes": [hero], "blue_heroes": ["Wasp"]}
    if scope is not None:
        body["history_scope"] = scope
    response = client.post("/games", json=body)
    assert response.status_code == 201, response.text
    data = response.json()
    game = client.app.state.registry.get(data["game_id"])
    token = game.hero_to_token[next(h for h in game.hero_to_token if h != "hero_wasp")]
    return game, {"Authorization": f"Bearer {token}"}


def capture(game, round_num, turn, phase, title):
    state = game.session.state
    state.round, state.turn, state.phase = round_num, turn, phase
    hero = next(iter(state.teams.values())).heroes[0]
    hero.title = title
    game.replay_recorder.record_cheat_gold(str(hero.id), 0, round_num, turn)
    return game.history.active[-1]


@pytest.mark.parametrize("scope", list(HistoryScope))
def test_game_creation_scope_and_spectator_exemption(client, scope):
    game, player = create(client, scope)
    base = f"/games/{game.game_id}"
    old = capture(game, 1, 1, GamePhase.RESOLUTION, "expired-frame")
    assert client.get(base + f"/history/state?position_id={old}", headers=player).status_code == 200
    current = capture(game, 2, 1, GamePhase.RESOLUTION, "visible-frame")
    spectator = {"Authorization": f"Bearer {game.spectator_token}"}
    player_index = client.get(base + "/history", headers=player).json()
    full_index = client.get(base + "/history", headers=spectator).json()
    allowed = scope == HistoryScope.EVERYTHING
    assert game.history_scope == scope
    assert player_index["scope"] == scope
    assert full_index["scope"] == "EVERYTHING"
    assert old in [p["position_id"] for p in full_index["positions"]]
    assert (old in [p["position_id"] for p in player_index["positions"]]) == allowed
    assert player_index["first_position_id"] == (game.history.active[0] if allowed else current)
    assert player_index["predecessor_id"] == (old if allowed else None)
    assert player_index["total"] == (len(game.history.active) if allowed else 1)
    for suffix in (
        f"/state?position_id={old}",
        f"/frames?from_position_id={old}",
        f"?before_position_id={old}",
    ):
        assert client.get(base + "/history" + suffix, headers=player).status_code == (
            200 if allowed else 403
        )
        assert client.get(base + "/history" + suffix, headers=spectator).status_code == 200
    assert client.get(base + "/history/state?position_id=99999", headers=player).status_code == 404
    response = client.get(base + f"/history/frames?from_position_id={current}", headers=player)
    assert response.status_code == 200
    assert "expired-frame" not in response.text
    assert response.json()["positions"][0]["position_id"] == current
    live = client.get(base, headers=player).json()["history"]
    assert live["scope"] == scope
    assert live["first_position_id"] == player_index["first_position_id"]
    token = player["Authorization"].split()[1]
    with client.websocket_connect(base + f"/ws?token={token}") as socket:
        assert socket.receive_json()["history"] == live
    with client.websocket_connect(base + f"/ws?token={game.spectator_token}") as socket:
        assert socket.receive_json()["history"]["scope"] == "EVERYTHING"
    # Reading access does not prune the audit captures or effective timeline.
    assert game.history.reader().read(old, "spectator")["view"]["teams"]
    assert old in game.history.active


def test_default_and_invalid_scope(client):
    game, player = create(client)
    assert game.history_scope == HistoryScope.CURRENT_ROUND
    assert (
        client.get(f"/games/{game.game_id}", headers=player).json()["history"]["scope"]
        == "CURRENT_ROUND"
    )
    for invalid in ("LAST_ROUND", "full", None, 1):
        assert (
            client.post(
                "/games",
                json={
                    "red_heroes": ["Arien"],
                    "blue_heroes": ["Wasp"],
                    "history_scope": invalid,
                },
            ).status_code
            == 422
        )


@pytest.mark.parametrize("scope", list(HistoryScope))
def test_round_grace_and_turn_cutoffs(client, scope):
    game, _player = create(client, scope)
    history = game.history
    old = capture(game, 1, 3, GamePhase.RESOLUTION, "turn-three")
    fourth = capture(game, 1, 4, GamePhase.RESOLUTION, "turn-four")
    assert (old in history.visible_active("hero_arien")) == (scope != HistoryScope.CURRENT_TURN)
    capture(game, 1, 4, GamePhase.LEVEL_UP, "upgrading")
    assert fourth in history.visible_active("hero_arien")
    epoch = history.epoch
    planning = capture(game, 2, 1, GamePhase.PLANNING, "selecting-next-round")
    assert (old in history.visible_active("hero_arien")) == (scope != HistoryScope.CURRENT_TURN)
    if scope == HistoryScope.CURRENT_ROUND:
        assert history.epoch == epoch  # Round increment alone does not expire round 1.
    capture(game, 2, 1, GamePhase.RESOLUTION, "revealed-next-round")
    assert (old in history.visible_active("hero_arien")) == (scope == HistoryScope.EVERYTHING)
    assert planning in history.visible_active("hero_arien")
    if scope == HistoryScope.CURRENT_ROUND:
        assert history.epoch > epoch
    assert old in history.visible_active(None)
    # A consensus rewind restores the window of the effective prefix too.
    state = game.session.state
    state.round, state.turn, state.phase = 1, 4, GamePhase.RESOLUTION
    state.get_hero("hero_arien").title = "turn-four"
    history.capture(game.session, history.raw_count + 1, {"type": "ov_rewind", "to": 2})
    assert fourth not in history.active  # The target head was replaced by the restored view.
    assert (old in history.visible_active("hero_arien")) == (scope != HistoryScope.CURRENT_TURN)


@pytest.mark.parametrize("scope", [HistoryScope.CURRENT_TURN, HistoryScope.CURRENT_ROUND])
def test_planning_grace_waits_for_two_card_hero_and_pass(client, scope):
    game, player = create(client, scope, hero="Emmitt")
    round_grace = scope == HistoryScope.CURRENT_ROUND
    old = capture(
        game,
        1,
        4 if round_grace else 1,
        GamePhase.LEVEL_UP if round_grace else GamePhase.RESOLUTION,
        "previous-period",
    )
    hero = game.session.state.get_hero("hero_emmitt")
    hero.level = 8
    assert hero.ultimate_card is not None
    capture(
        game, 2 if round_grace else 1, 1 if round_grace else 2, GamePhase.PLANNING, "next-planning"
    )
    base = f"/games/{game.game_id}"
    assert (
        client.post(base + "/cards", headers=player, json={"card_id": hero.hand[0].id}).status_code
        == 200
    )
    wasp = {"Authorization": f"Bearer {game.hero_to_token['hero_wasp']}"}
    game.session.state.get_hero("hero_wasp").hand.clear()
    assert client.post(base + "/pass", headers=wasp).status_code == 200
    assert game.session.state.phase == GamePhase.PLANNING
    assert client.get(base + f"/history/state?position_id={old}", headers=player).status_code == 200
    assert client.post(base + "/planning-done", headers=player).status_code == 200
    assert game.session.state.phase == GamePhase.RESOLUTION
    assert client.get(base + f"/history/state?position_id={old}", headers=player).status_code == 403


def test_current_turn_retains_previous_turn_until_last_normal_commit(client):
    game, player = create(client, HistoryScope.CURRENT_TURN)
    old = capture(game, 1, 1, GamePhase.RESOLUTION, "last-turn")
    epoch = game.history.epoch
    capture(game, 1, 2, GamePhase.PLANNING, "selecting-next-turn")
    assert game.history.epoch == epoch
    base = f"/games/{game.game_id}"
    for hero_id in ("hero_arien", "hero_wasp"):
        assert (
            client.get(base + f"/history/state?position_id={old}", headers=player).status_code
            == 200
        )
        hero = game.session.state.get_hero(hero_id)
        response = client.post(
            base + "/cards",
            headers={"Authorization": f"Bearer {game.hero_to_token[hero_id]}"},
            json={"card_id": hero.hand[0].id},
        )
        assert response.status_code == 200
    assert game.session.state.phase == GamePhase.RESOLUTION
    assert client.get(base + f"/history/state?position_id={old}", headers=player).status_code == 403


@pytest.mark.parametrize("scope", list(HistoryScope))
def test_scope_and_window_survive_restart_and_missing_legacy_setting(client, scope):
    game, _player = create(client, scope)
    capture(game, 1, 4, GamePhase.LEVEL_UP, "old-round")
    capture(game, 2, 1, GamePhase.PLANNING, "new-planning")
    registry = client.app.state.registry
    registry.save_game(game.game_id)
    restored = GameRegistry(registry._save_dir)
    assert restored.restore_all() == 1
    again = restored.get(game.game_id)
    assert again.history_scope == again.history.scope == scope
    assert again.history.visible_active("hero_arien") == game.history.visible_active("hero_arien")
    path = Path(registry._save_dir) / f"{game.game_id}.json"
    saved = json.loads(path.read_text())
    saved.pop("history_scope")
    path.write_text(json.dumps(saved))
    legacy = GameRegistry(registry._save_dir)
    assert legacy.restore_all() == 1
    assert legacy.get(game.game_id).history_scope == HistoryScope.CURRENT_ROUND


@pytest.mark.parametrize("stage", ["materialize", "encode"])
def test_window_is_rechecked_after_async_work_even_without_capture(client, monkeypatch, stage):
    game, player = create(client, HistoryScope.CURRENT_TURN)
    position = capture(game, 1, 1, GamePhase.RESOLUTION, "expired-while-reading")
    if stage == "materialize":
        original = live_history.HistoryReader.read

        def advancing(*args, **kwargs):
            result = original(*args, **kwargs)
            game.session.state.turn = 2
            return result

        monkeypatch.setattr(live_history.HistoryReader, "read", advancing)
        endpoint = f"state?position_id={position}"
    else:
        original = routes_history.encode

        def advancing(*args, **kwargs):
            result = original(*args, **kwargs)
            game.session.state.turn = 2
            return result

        monkeypatch.setattr(routes_history, "encode", advancing)
        endpoint = f"frames?from_position_id={position}"
    response = client.get(f"/games/{game.game_id}/history/{endpoint}", headers=player)
    assert response.status_code == 403
    assert "expired-while-reading" not in response.text
    index = client.get(f"/games/{game.game_id}/history", headers=player).json()
    assert index["total"] == 0
    assert index["first_position_id"] is index["predecessor_id"] is index["position_id"] is None


def test_backfill_preserves_configured_scope(client, monkeypatch):
    game, player = create(client, HistoryScope.CURRENT_TURN)
    hero = game.session.state.get_hero("hero_arien")
    assert (
        client.post(
            f"/games/{game.game_id}/cards", headers=player, json={"card_id": hero.hand[0].id}
        ).status_code
        == 200
    )

    async def inline(fn, *args):
        return fn(*args)

    monkeypatch.setattr(history_backfill, "run_heavy", inline)
    game.history.backfill_status = "pending"
    asyncio.run(history_backfill.ensure_backfill(game, client.app.state.registry))
    assert game.history.backfill_status == "complete"
    assert game.history.scope == HistoryScope.CURRENT_TURN
