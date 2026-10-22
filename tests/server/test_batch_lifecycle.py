"""Batch lifecycle contracts through real server, save and replay boundaries."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goa2.bootstrap import register_all_effects
from goa2.domain.input import InputResponse, selection_value
from goa2.domain.models import GamePhase
from goa2.engine.handler import push_steps
from goa2.engine.persistence import load_game
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.engine.steps import PlaceRunesStep, ResolveUpgradesStep, SetContextFlagStep
from goa2.server.app import create_app
from goa2.server.replay import ReplayRecorder, replay_game


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key, folder in [("SAVE", "saves"), ("REPLAY", "replays"), ("LOG", "logs")]:
        monkeypatch.setenv(f"GOA2_{key}_DIR", str(tmp_path / folder))
    with TestClient(create_app()) as client:
        yield client


def _game(client, choice):
    name = "Arien" if choice == "upgrades" else "Snorri"
    response = client.post(
        "/games",
        json={"map_name": "forgotten_island", "red_heroes": [name], "blue_heroes": ["Wasp"]},
    )
    assert response.status_code == 201
    data = response.json()
    game = client.app.state.registry.get(data["game_id"])
    hero = f"hero_{name.lower()}"
    tokens = {p["hero_id"]: p["token"] for p in data["player_tokens"]}
    state = game.session.state
    if choice == "upgrades":
        state.phase = GamePhase.LEVEL_UP
        state.pending_upgrades.update({hero: 3, "hero_wasp": 3})
        step = ResolveUpgradesStep()
    else:
        state.phase = GamePhase.RESOLUTION
        state.current_actor_id = hero
        state.resolution_owner_id = hero
        step = PlaceRunesStep(hero_id=hero)
    # Isolate the real step's lifecycle; don't fabricate client prompts.
    push_steps(state, [step, SetContextFlagStep(key="batch_finished", value=True)])
    game.last_result = game.session.advance()
    return game, hero, tokens


def _view(client, game, token):
    response = client.get(f"/games/{game.game_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return response.json()


def _submit(client, game, token, selection, request_id, transport="rest", accepted=True):
    payload = {"request_id": request_id, "selection": selection}
    if transport == "rest":
        response = client.post(
            f"/games/{game.game_id}/input",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == (200 if accepted else 400), response.text
    else:
        with client.websocket_connect(f"/games/{game.game_id}/ws?token={token}") as ws:
            assert ws.receive_json()["type"] == "STATE_UPDATE"
            ws.send_json({"type": "SUBMIT_INPUT", **payload})
            result = ws.receive_json()
            assert result["type"] == ("ACTION_RESULT" if accepted else "ERROR"), result
            if accepted:
                assert ws.receive_json()["type"] == "STATE_UPDATE"


@pytest.mark.parametrize("transport", ["rest", "websocket"])
@pytest.mark.parametrize("choice", ["upgrades", "runes"])
def test_partial_progress_survives_save_resume_and_duplicate_delivery(client, choice, transport):
    game, hero, tokens = _game(client, choice)
    token = tokens[hero]
    request = _view(client, game, token)["input_request"]
    first = request["players"][hero]["options"][0]["pair"][0] if choice == "upgrades" else "axe"
    single = {"hero_id": hero, "card_id": first} if choice == "upgrades" else first
    _submit(client, game, token, single, request["request_id"], transport)
    partial = _view(client, game, token)["input_request"]
    assert partial["request_id"] != request["request_id"]
    if choice == "upgrades":
        assert partial["players"][hero]["remaining"] == 2
        assert partial["players"][hero]["selection_counts"] == [1, 2]
    else:
        assert partial["next_slot"] == 2
        assert partial["max_selections"] == 3
        assert partial["selection_counts"] == [1, 2, 3]
    registry = client.app.state.registry
    registry.save_game(game.game_id)
    loaded = load_game(str(Path(registry._save_dir) / f"{game.game_id}.json"))
    game_id = game.game_id
    registry._games.pop(game_id)
    assert registry.restore_all() == 1
    game = registry.get(game_id)
    assert _view(client, game, token)["input_request"] == partial
    assert game.replay_recorder.records == loaded["replay_log"]
    before = game.session.state.model_dump(mode="json")
    records = list(game.replay_recorder.records)
    _submit(client, game, token, single, request["request_id"], transport, accepted=False)
    assert game.session.state.model_dump(mode="json") == before
    assert game.replay_recorder.records == records
    invalid = (
        {"hero_id": hero, "card_ids": ["invalid", "invalid"]}
        if choice == "upgrades"
        else ["axe", "bird"]
    )
    _submit(client, game, token, invalid, partial["request_id"], transport, accepted=False)
    assert game.session.state.model_dump(mode="json") == before
    assert _view(client, game, token)["input_request"] == partial
    ids = (
        [option["pair"][0] for option in partial["players"][hero]["options"][:2]]
        if choice == "upgrades"
        else ["horn", "bird"]
    )
    batch = {"hero_id": hero, "card_ids": ids} if choice == "upgrades" else ids
    _submit(client, game, token, batch, partial["request_id"], transport)
    completed = game.session.state.model_dump(mode="json")
    records = list(game.replay_recorder.records)
    _submit(client, game, token, batch, partial["request_id"], transport, accepted=False)
    assert game.session.state.model_dump(mode="json") == completed
    assert game.replay_recorder.records == records
    assert len([r for r in records if r["type"] == "input"]) == 2
    if choice == "upgrades":
        assert hero not in game.session.state.pending_upgrades
    else:
        assert [
            r.value for _, r in sorted(game.session.state.get_hero(hero).rune_slots.items())
        ] == ["axe", "horn", "bird", "anvil"]
        assert game.session.state.execution_context["batch_finished"] is True


@pytest.mark.parametrize("transport", ["rest", "websocket"])
def test_other_player_refreshes_upgrade_request_without_spending_stale_batch(client, transport):
    game, hero, tokens = _game(client, "upgrades")
    original = _view(client, game, tokens[hero])["input_request"]
    assert set(original["players"]) == {hero}
    other = _view(client, game, tokens["hero_wasp"])["input_request"]
    _submit(
        client,
        game,
        tokens["hero_wasp"],
        {"hero_id": "hero_wasp", "card_id": other["players"]["hero_wasp"]["options"][0]["pair"][0]},
        other["request_id"],
        transport,
    )
    fresh = _view(client, game, tokens[hero])["input_request"]
    assert fresh["request_id"] != original["request_id"]
    assert fresh["players"] == original["players"]
    ids = [option["pair"][0] for option in fresh["players"][hero]["options"][:3]]
    batch = {"hero_id": hero, "card_ids": ids}
    before = game.session.state.model_dump(mode="json")
    _submit(client, game, tokens[hero], batch, original["request_id"], transport, accepted=False)
    assert game.session.state.model_dump(mode="json") == before
    _submit(client, game, tokens[hero], batch, fresh["request_id"], transport)
    assert hero not in game.session.state.pending_upgrades
    assert game.session.state.pending_upgrades["hero_wasp"] == 2


def test_concurrent_upgrade_batches_refresh_the_losing_players_offer(client):
    game, hero, tokens = _game(client, "upgrades")
    pending = {}
    for owner in [hero, "hero_wasp"]:
        request = _view(client, game, tokens[owner])["input_request"]
        pending[owner] = {
            "request_id": request["request_id"],
            "selection": {
                "hero_id": owner,
                "card_ids": [o["pair"][0] for o in request["players"][owner]["options"][:3]],
            },
        }

    def post(owner):
        return (
            owner,
            client.post(
                f"/games/{game.game_id}/input",
                json=pending[owner],
                headers={"Authorization": f"Bearer {tokens[owner]}"},
            ).status_code,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = dict(pool.map(post, pending))
    assert sorted(outcomes.values()) == [200, 400]
    loser = next(owner for owner, status in outcomes.items() if status == 400)
    assert game.session.state.pending_upgrades == {loser: 3}
    fresh = _view(client, game, tokens[loser])["input_request"]
    assert fresh["request_id"] != pending[loser]["request_id"]
    _submit(client, game, tokens[loser], pending[loser]["selection"], fresh["request_id"])
    assert not game.session.state.pending_upgrades


def _stable(value):
    if isinstance(value, dict):
        return {
            k: _stable(v)
            for k, v in value.items()
            if k not in {"step_id", "pending_request_id", "request_id", "active_request_id"}
        }
    if isinstance(value, list):
        return [_stable(v) for v in value]
    return value


def test_seeded_rune_and_upgrade_batches_replay_with_rollback(tmp_path):
    """Play registered cards from real setup, not a patched replay checkpoint."""
    register_all_effects()
    live = GameSession(
        GameSetup.create_game(
            "src/goa2/data/maps/forgotten_island.json", ["Snorri"], ["Wasp"], seed=11
        )
    )
    rec = ReplayRecorder("batch-replay", str(tmp_path))
    rec.record_setup(
        map_name="forgotten_island",
        red_heroes=["Snorri"],
        blue_heroes=["Wasp"],
        game_type="LONG",
        cheats=False,
        seed=11,
    )
    # A recorded legacy gold change makes multiple upgrades available in round 1.
    live.state.get_hero("hero_snorri").gold += 7
    rec.record_cheat_gold("hero_snorri", 7, 1, 1)
    result = None
    rune_batches = upgrade_batches = 0
    rolled_back = False
    for _ in range(120):
        state = live.state
        if state.phase == GamePhase.PLANNING:
            for hero_id in ["hero_snorri", "hero_wasp"]:
                hero = state.get_hero(hero_id)
                card = next((c for c in hero.hand if c.id == "inscribe_the_runes"), hero.hand[0])
                rec.record_commit(hero_id, card.id, state.round, state.turn)
                result = live.commit_card(hero_id, card)
        elif result and result.input_request:
            req = result.input_request
            if req.request_type.value == "UPGRADE_PHASE":
                hero_id, data = next(iter(req.context["players"].items()))
                ids = [opt["pair"][0] for opt in data["options"][: data["remaining"]]]
                selection = {"hero_id": hero_id, "card_ids": ids}
                upgrade_batches += 1
            elif req.context.get("supports_batch") and req.context.get("next_slot"):
                selection = [option.id for option in req.options[:3]]
                rune_batches += 1
            else:
                positive_options = [o for o in req.options if o.id not in {"ROLLBACK", "NO"}]
                selection = next(
                    (o.id for o in positive_options if o.id == "HOLD"),
                    selection_value(positive_options[0]),
                )
                actor = state.get_hero(state.current_actor_id) if state.current_actor_id else None
                if (
                    actor
                    and actor.current_turn_card
                    and actor.current_turn_card.id == "inscribe_the_runes"
                    and any(o.id == "SKILL" for o in req.options)
                    and req.request_type.value == "CHOOSE_ACTION"
                ):
                    selection = "SKILL"
            rec.record_input(req.player_id, selection, state.round, state.turn)
            result = live.advance(InputResponse(request_id=req.id, selection=selection))
            if rune_batches == 1 and not rolled_back:
                rec.record_rollback("hero_snorri", state.round, state.turn)
                result = live.rollback()
                rolled_back = True
            if upgrade_batches:
                break
        else:
            result = live.advance()
    assert rune_batches == 2 and rolled_back and upgrade_batches == 1
    replayed = replay_game(str(rec.path))
    assert _stable(replayed.state.model_dump(mode="json")) == _stable(
        live.state.model_dump(mode="json")
    )
    inputs = [
        json.loads(line)
        for line in rec.path.read_text().splitlines()
        if json.loads(line)["type"] == "input"
    ]
    assert any(isinstance(r["sel"], list) for r in inputs)
    assert any(isinstance(r["sel"], dict) and "card_ids" in r["sel"] for r in inputs)
