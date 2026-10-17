"""Webhook API, decision semantics, privacy, and isolated outbound delivery."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from goa2.domain.input import InputRequestType, create_input_request
from goa2.domain.models import GamePhase, TeamColor
from goa2.domain.time_control import TimeControlConfig, create_game_clock
from goa2.engine.session import SessionResult, SessionResultType
from goa2.engine.steps.selection import SelectStep
from goa2.engine.steps.utility import MayRepeatNTimesStep
from goa2.server.app import create_app
from goa2.server.registry import GameRegistry
from goa2.server.webhooks import (
    WebhookConfig,
    WebhookDispatcher,
    observe_game,
    resolve_public_addresses,
    waiting_heroes,
)

USER_ID = "123456789012345678"
OTHER_ID = "234567890123456789"
HOOK = {"url": "https://discord.com/api/webhooks/123/secret-token", "format": "discord"}
JSON_HOOK = {"url": "https://example.com/callback/secret-token", "format": "json"}


@pytest.fixture
def api(monkeypatch):
    sent = []
    monkeypatch.setattr(
        WebhookDispatcher, "enqueue", lambda self, gid, config, payload: sent.append(payload)
    )
    with TestClient(create_app()) as client:
        yield client, sent


def create_game(client, webhook=JSON_HOOK, **extra):
    response = client.post(
        "/games",
        json={
            "red_heroes": ["Hanu"],
            "blue_heroes": ["Arien"],
            "player_names": {"Hanu": "Sebastian", "Arien": "Alex"},
            "discord_user_ids": {"Hanu": USER_ID, "Arien": OTHER_ID},
            "webhook": webhook,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return client.app.state.registry.get(data["game_id"]), data


def auth(game, hero="hero_hanu"):
    return {"Authorization": f"Bearer {game.hero_to_token[hero]}"}


def set_request(game, player_id, **context):
    game.session.state.phase = GamePhase.RESOLUTION
    game.last_result = SessionResult(
        result_type=SessionResultType.INPUT_NEEDED,
        current_phase=GamePhase.RESOLUTION,
        input_request=create_input_request(
            InputRequestType.SELECT_OPTION,
            player_id=player_id,
            prompt="Private prompt",
            options=["secret-choice"],
            **context,
        ),
    )


def test_initial_discord_mentions_and_no_secret_exposure(api, caplog):
    client, sent = api
    game, data = create_game(client, HOOK)
    assert len(sent) == 1
    assert sent[0] == {
        "content": f"Game created. Waiting for Arien (Alex) <@{OTHER_ID}>, Hanu (Sebastian) <@{USER_ID}>.",
        "allowed_mentions": {"parse": [], "users": [USER_ID, OTHER_ID]},
    }
    assert "secret-token" not in json.dumps(data)
    view = client.get(f"/games/{game.game_id}", headers=auth(game)).json()
    assert "webhook" not in json.dumps(view)
    assert "secret-token" not in caplog.text
    assert game.replay_recorder
    assert "secret-token" not in json.dumps(game.replay_recorder.records)


def test_rest_mutation_rejection_and_repeated_saves(api):
    client, sent = api
    game, _ = create_game(client)
    registry = client.app.state.registry
    initial = len(sent)
    registry.save_game(game.game_id)
    client.get(f"/games/{game.game_id}", headers=auth(game))
    bad = client.post(
        f"/games/{game.game_id}/cards", headers=auth(game), json={"card_id": "missing"}
    )
    assert bad.status_code == 404
    assert len(sent) == initial
    hero = game.session.state.get_hero("hero_hanu")
    result = client.post(
        f"/games/{game.game_id}/cards", headers=auth(game), json={"card_id": hero.hand[0].id}
    )
    assert result.status_code == 200
    assert len(sent) == initial + 1
    assert [h["hero_id"] for h in sent[-1]["awaiting_heroes"]] == ["hero_arien"]
    assert set(sent[-1]) == {
        "version",
        "event_id",
        "game_id",
        "event",
        "occurred_at",
        "round",
        "turn",
        "phase",
        "awaiting_heroes",
        "winner",
        "message",
    }
    assert "secret-choice" not in json.dumps(sent)


def test_ws_mutation_and_reconnect(api):
    client, sent = api
    game, _ = create_game(client)
    hero = game.session.state.get_hero("hero_hanu")
    initial = len(sent)
    with client.websocket_connect(
        f"/games/{game.game_id}/ws?token={game.hero_to_token['hero_hanu']}"
    ) as ws:
        assert ws.receive_json()["type"] == "STATE_UPDATE"
        assert len(sent) == initial
        ws.send_json({"type": "COMMIT_CARD", "card_id": hero.hand[0].id})
        assert ws.receive_json()["type"] == "ACTION_RESULT"
        assert len(sent) == initial + 1
    with client.websocket_connect(f"/games/{game.game_id}/ws?token={game.spectator_token}") as ws:
        ws.receive_json()
    assert len(sent) == initial + 1


def test_quiet_mode_uses_controller_and_new_turn_boundaries(api):
    client, _ = api
    game, _ = create_game(client, HOOK)
    game.session.state.current_actor_id = "hero_arien"
    set_request(game, "hero_hanu")
    payload = observe_game(game)
    assert payload["content"] == f"Hanu (Sebastian) <@{USER_ID}>'s turn."
    assert payload["allowed_mentions"]["users"] == [USER_ID]
    # A different prompt for the same controller is still the same decision maker.
    set_request(game, "hero_hanu")
    assert observe_game(game) is None
    game.session.state.turn += 1
    assert observe_game(game) is not None
    game.session.state.winner = TeamColor.RED
    game.session.state.phase = GamePhase.GAME_OVER
    assert observe_game(game)["content"] == "Game over. RED wins."
    assert observe_game(game) is None


def test_team_and_simultaneous_waiting(api):
    client, _ = api
    game, _ = create_game(client)
    set_request(game, "team:RED")
    assert waiting_heroes(game) == ["hero_hanu"]
    set_request(game, "simultaneous", players={"hero_hanu": {}, "hero_arien": {}})
    assert waiting_heroes(game) == ["hero_arien", "hero_hanu"]
    game.last_result.input_request.context["players"].pop("hero_arien")
    assert waiting_heroes(game) == ["hero_hanu"]


def test_responder_change_without_other_state_changes(api):
    client, _ = api
    game, _ = create_game(client)
    set_request(game, "hero_hanu")
    observe_game(game)
    set_request(game, "hero_arien")
    assert [h["hero_id"] for h in observe_game(game)["awaiting_heroes"]] == ["hero_arien"]


def test_invalid_selection_does_not_notify_but_valid_progress_does(api):
    client, sent = api
    game, _ = create_game(client, {**JSON_HOOK, "mode": "state_changes"})
    state = game.session.state
    state.phase = GamePhase.RESOLUTION
    state.current_actor_id = "hero_hanu"
    state.execution_stack = [
        SelectStep(target_type="NUMBER", prompt="Choose 1 or 2", number_options=[1, 2])
    ]
    game.last_result = game.session.advance()
    observe_game(game, baseline_only=True)
    initial = len(sent)
    first_request = game.last_result.input_request

    response = client.post(
        f"/games/{game.game_id}/input",
        headers=auth(game),
        json={"request_id": first_request.id, "selection": 999},
    )
    assert response.status_code == 200
    next_request = game.last_result.input_request
    assert next_request.id != first_request.id
    assert next_request.prompt == first_request.prompt
    assert next_request.options == first_request.options
    assert len(sent) == initial

    response = client.post(
        f"/games/{game.game_id}/input",
        headers=auth(game),
        json={"request_id": next_request.id, "selection": 1},
    )
    assert response.status_code == 200
    assert state.execution_context["selection"] == 1
    assert len(sent) == initial + 1


def test_nested_steps_and_input_stack_ignore_request_ids(api):
    client, _ = api
    game, _ = create_game(client, {**JSON_HOOK, "mode": "state_changes"})
    repeat = MayRepeatNTimesStep(
        steps_template=[SelectStep(target_type="NUMBER", prompt="Choose", number_options=[1, 2])]
    )
    state = game.session.state
    state.execution_stack = [repeat]
    request = create_input_request(
        InputRequestType.SELECT_NUMBER, player_id="hero_hanu", prompt="Choose"
    )
    state.input_stack = [request]
    observe_game(game, baseline_only=True)
    repeat.pending_request_id = "new-repeat-request"
    repeat.steps_template[0].pending_request_id = "new-nested-request"
    request.id = "new-stack-request"
    assert observe_game(game) is None
    repeat.repeats_done += 1
    assert observe_game(game)["event"] == "state_changed"


def test_second_card_planning_stays_open_until_done(api):
    client, sent = api
    game, _ = create_game(client, red_heroes=["Emmitt"])
    game.session.state.get_hero("hero_emmitt").level = 8
    observe_game(game, baseline_only=True)
    initial = len(sent)
    response = client.post(
        f"/games/{game.game_id}/cards",
        headers=auth(game, "hero_emmitt"),
        json={"card_id": "reverse_time"},
    )
    assert response.status_code == 200
    assert waiting_heroes(game) == ["hero_arien", "hero_emmitt"]
    assert len(sent) == initial
    response = client.post(
        f"/games/{game.game_id}/planning-done", headers=auth(game, "hero_emmitt")
    )
    assert response.status_code == 200
    assert len(sent) == initial + 1
    assert [h["hero_id"] for h in sent[-1]["awaiting_heroes"]] == ["hero_arien"]


def test_deadline_worker_emits_without_connected_clients(api):
    from goa2.server.time_control import _deadline_worker

    client, sent = api
    config = {
        "planning_allowance_seconds": 3600,
        "resolution_allowance_seconds": 3600,
        "response_grant_seconds": 10,
        "initial_time_bank_seconds": 0,
        "time_bank_increment_seconds": 0,
        "max_time_bank_seconds": 0,
        "upgrade_allowance_seconds": 10,
    }
    game, _ = create_game(client, time_control=config)
    for hero in ("hero_hanu", "hero_arien"):
        response = client.post(
            f"/games/{game.game_id}/ready", json={"ready": True}, headers=auth(game, hero)
        )
        assert response.status_code == 200
    initial = len(sent)
    clock = game.session.state.clock
    clock.players["hero_hanu"].planning_allowance_ms = 0
    client.portal.call(_deadline_worker, game, client.app.state.registry, clock.revision, 0)
    assert "hero_hanu" in game.session.state.pending_inputs
    assert len(sent) == initial + 1
    assert [h["hero_id"] for h in sent[-1]["awaiting_heroes"]] == ["hero_arien"]


def test_rollback_emits_restored_state(api):
    client, sent = api
    game, _ = create_game(client, {**JSON_HOOK, "mode": "state_changes"})
    game.session.state.current_actor_id = "hero_hanu"
    set_request(game, "hero_hanu")
    game.session._rollback_snapshot = game.session._make_snapshot()
    game.session._rollback_actor_id = "hero_hanu"
    before = game.session.state.get_hero("hero_hanu").gold
    game.session.state.get_hero("hero_hanu").gold += 5
    observe_game(game, baseline_only=True)
    initial = len(sent)
    response = client.post(f"/games/{game.game_id}/rollback", headers=auth(game))
    assert response.status_code == 200
    assert game.session.state.get_hero("hero_hanu").gold == before
    assert len(sent) == initial + 1


def test_override_emits_one_update(api):
    client, sent = api
    game, _ = create_game(client, {**JSON_HOOK, "mode": "state_changes"})
    initial = len(sent)
    with client.websocket_connect(
        f"/games/{game.game_id}/ws?token={game.hero_to_token['hero_hanu']}"
    ) as ws:
        ws.receive_json()
        ws.send_json(
            {
                "type": "PROPOSE_OVERRIDE",
                "family": "patch",
                "op": "set_gold",
                "args": {"hero_id": "hero_hanu", "value": 9},
            }
        )
        for _ in range(4):
            message = ws.receive_json()
            if message["type"] == "STATE_UPDATE":
                break
        assert message["type"] == "STATE_UPDATE"
        assert game.session.state.get_hero("hero_hanu").gold == 9
        assert len(sent) == initial + 1


def test_frequent_mode_and_clock_bookkeeping(api):
    client, _ = api
    game, _ = create_game(client, {**JSON_HOOK, "mode": "state_changes"})
    game.session.state.get_hero("hero_hanu").gold += 1
    payload = observe_game(game)
    assert payload["event"] == "state_changed"
    assert payload["message"].startswith("Board updated.")
    assert observe_game(game) is None
    config = TimeControlConfig(
        planning_allowance_seconds=10,
        resolution_allowance_seconds=10,
        response_grant_seconds=10,
        initial_time_bank_seconds=10,
        time_bank_increment_seconds=0,
        max_time_bank_seconds=10,
        upgrade_allowance_seconds=10,
    )
    game.session.state.clock = create_game_clock(
        config, game.hero_to_token, round_number=1, turn_number=1
    )
    observe_game(game, baseline_only=True)
    game.session.state.clock.revision += 1
    game.session.state.clock.last_settled_at_ms = 123456
    assert observe_game(game) is None
    game.session.state.clock.ready_hero_ids.append("hero_hanu")
    assert [h["hero_id"] for h in observe_game(game)["awaiting_heroes"]] == ["hero_arien"]


def test_discord_only_mentions_explicit_ids_and_escapes_names(api):
    client, _ = api
    game, _ = create_game(
        client, HOOK, player_names={"Hanu": "@everyone **hi**"}, discord_user_ids={}
    )
    set_request(game, "hero_hanu")
    payload = observe_game(game)
    assert payload["allowed_mentions"] == {"parse": [], "users": []}
    assert "\\*\\*hi\\*\\*" in payload["content"]


@pytest.mark.parametrize(
    "webhook",
    [
        {**JSON_HOOK, "url": "http://example.com/secret-token"},
        {**JSON_HOOK, "url": "https://127.0.0.1/secret-token"},
        {**JSON_HOOK, "url": "https://[::1]/secret-token"},
        {**JSON_HOOK, "url": "https://localhost/secret-token"},
        {**JSON_HOOK, "url": "https://user:password@example.com/secret-token"},
        {**HOOK, "url": "https://discord.com.evil.example/api/webhooks/123/secret-token"},
        {**HOOK, "format": "invalid"},
        {**HOOK, "mode": "invalid"},
    ],
)
def test_invalid_configuration_never_echoes_url(api, webhook):
    client, _ = api
    response = client.post(
        "/games", json={"red_heroes": ["Hanu"], "blue_heroes": ["Arien"], "webhook": webhook}
    )
    assert response.status_code == 422
    assert "secret-token" not in response.text


def test_invalid_discord_id_is_rejected(api):
    client, _ = api
    response = client.post(
        "/games",
        json={
            "red_heroes": ["Hanu"],
            "blue_heroes": ["Arien"],
            "discord_user_ids": {"Hanu": "@name"},
        },
    )
    assert response.status_code == 422


def test_persistence_restore_is_silent_and_legacy_is_disabled(api, tmp_path):
    client, _ = api
    game, _ = create_game(client)
    registry = client.app.state.registry
    path = tmp_path / f"{game.game_id}.json"
    # Use an isolated second registry so the app never attempts actual delivery.
    registry._save_dir = str(tmp_path)
    registry.save_game(game.game_id)
    restored = GameRegistry(str(tmp_path))
    assert restored.restore_all() == 1
    loaded = restored.get(game.game_id)
    assert loaded.webhook.url.get_secret_value() == JSON_HOOK["url"]
    assert loaded.discord_user_ids == game.discord_user_ids
    assert observe_game(loaded) is None
    saved = json.loads(path.read_text())
    saved.pop("webhook")
    saved.pop("discord_user_ids")
    path.write_text(json.dumps(saved))
    legacy = GameRegistry(str(tmp_path))
    assert legacy.restore_all() == 1
    assert legacy.get(game.game_id).webhook is None


def test_lobby_settings_privacy_permissions_and_transfer(api):
    client, sent = api
    response = client.post(
        "/drafts", json={"host_name": "Sebastian", "discord_user_id": USER_ID, "webhook": HOOK}
    )
    assert response.status_code == 201
    draft = response.json()
    did = draft["draft_id"]
    host = {"Authorization": f"Bearer {draft['player_token']}"}
    join = client.post(
        f"/drafts/{did}/join", json={"display_name": "Alex", "discord_user_id": OTHER_ID}
    ).json()
    guest = {"Authorization": f"Bearer {join['player_token']}"}
    md = client.app.state.draft_registry.get(did)
    assert (
        client.patch(f"/drafts/{did}/settings", headers=guest, json={"webhook": None}).status_code
        == 403
    )
    assert (
        client.patch(
            f"/drafts/{did}/settings", headers=host, json={"game_type": "QUICK"}
        ).status_code
        == 200
    )
    assert md.webhook is not None
    assert (
        client.patch(f"/drafts/{did}/settings", headers=host, json={"webhook": None}).status_code
        == 200
    )
    assert md.webhook is None
    assert (
        client.patch(f"/drafts/{did}/settings", headers=host, json={"webhook": HOOK}).status_code
        == 200
    )
    view = client.get(f"/drafts/{did}", headers=host).json()
    assert "secret-token" not in json.dumps(view)
    assert not sent
    # Exercise the actual claim-to-game bridge with a completed draft state.
    from goa2.draft.models import DraftStatus
    from goa2.server.routes_draft import _maybe_create_game

    md.state.status = DraftStatus.CLAIMING
    md.state.players[0].team = TeamColor.RED
    md.state.players[0].claimed_hero = "Hanu"
    md.state.players[1].team = TeamColor.BLUE
    md.state.players[1].claimed_hero = "Arien"
    md.state.picks = {TeamColor.RED: ["Hanu"], TeamColor.BLUE: ["Arien"]}
    from starlette.requests import Request

    _maybe_create_game(Request({"type": "http", "app": client.app}), md)
    game = client.app.state.registry.get(md.state.game_id)
    assert game.discord_user_ids == {"hero_hanu": USER_ID, "hero_arien": OTHER_ID}
    assert game.webhook == md.webhook
    assert len(sent) == 1
    assert (
        client.patch(f"/drafts/{did}/settings", headers=host, json={"webhook": None}).status_code
        == 409
    )


def test_dns_rejects_mixed_public_private_and_pins_public(monkeypatch):
    async def run():
        loop = asyncio.get_running_loop()
        resolver = AsyncMock(
            return_value=[
                (2, 1, 6, "", ("8.8.8.8", 443)),
                (2, 1, 6, "", ("8.8.8.8", 443)),
                (2, 1, 6, "", ("1.1.1.1", 443)),
            ]
        )
        monkeypatch.setattr(loop, "getaddrinfo", resolver)
        assert await resolve_public_addresses("example.com", 443) == ["8.8.8.8", "1.1.1.1"]
        resolver.return_value.append((2, 1, 6, "", ("127.0.0.1", 443)))
        with pytest.raises(ValueError):
            await resolve_public_addresses("example.com", 443)

    asyncio.run(run())


@pytest.mark.parametrize(
    "statuses, expected",
    [([204], 1), ([429, 500, 204], 3), ([503, 503, 503], 3), ([400], 1), ([302], 1)],
)
def test_delivery_retries_pins_tls_and_hides_credentials(monkeypatch, caplog, statuses, expected):
    async def run():
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(statuses[len(requests) - 1], headers={"Retry-After": "0"})

        monkeypatch.setattr(
            "goa2.server.webhooks.resolve_public_addresses", AsyncMock(return_value=["8.8.8.8"])
        )
        monkeypatch.setattr("goa2.server.webhooks.asyncio.sleep", AsyncMock())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            dispatcher = WebhookDispatcher(client)
            await dispatcher._deliver("game", WebhookConfig(**HOOK), {"content": "hello"}, "event")
        assert len(requests) == expected
        for request in requests:
            assert request.url.host == "8.8.8.8"
            assert request.headers["Host"] == "discord.com"
            assert request.headers["X-GoA2-Event-ID"] == "event"
            assert request.extensions["sni_hostname"] == "discord.com"
            assert request.url.params["wait"] == "true"

    with caplog.at_level(logging.INFO):
        asyncio.run(run())
    assert "secret-token" not in caplog.text


def test_callback_cookies_are_neither_stored_nor_forwarded(monkeypatch):
    async def run():
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(
                204, headers={"Set-Cookie": "callback_session=private-value; Path=/; Secure"}
            )

        monkeypatch.setattr(
            "goa2.server.webhooks.resolve_public_addresses", AsyncMock(return_value=["8.8.8.8"])
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), cookies={"preexisting": "private-value"}
        ) as client:
            dispatcher = WebhookDispatcher(client)
            for host in ("first.example", "second.example", "first.example"):
                await dispatcher._deliver(
                    host, WebhookConfig(url=f"https://{host}/hook", format="json"), {}, "event"
                )
                assert not client.cookies
            assert [r.headers["Host"] for r in requests] == [
                "first.example",
                "second.example",
                "first.example",
            ]
            assert all("Cookie" not in request.headers for request in requests)

    asyncio.run(run())


@pytest.mark.parametrize("failure_type", [httpx.ConnectError, httpx.ConnectTimeout])
def test_delivery_falls_back_to_ipv4_with_original_tls_identity(monkeypatch, failure_type):
    async def run():
        requests = []

        def handle(request):
            requests.append(request)
            if request.url.host == "2001:4860:4860::8888":
                raise failure_type("unreachable IPv6")
            return httpx.Response(204)

        resolver = AsyncMock(return_value=["2001:4860:4860::8888", "8.8.8.8"])
        sleep = AsyncMock()
        monkeypatch.setattr("goa2.server.webhooks.resolve_public_addresses", resolver)
        monkeypatch.setattr("goa2.server.webhooks.asyncio.sleep", sleep)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await WebhookDispatcher(client)._deliver("game", WebhookConfig(**HOOK), {}, "event")
        assert [r.url.host for r in requests] == ["2001:4860:4860::8888", "8.8.8.8"]
        resolver.assert_awaited_once()
        sleep.assert_not_awaited()
        assert 0 < requests[0].extensions["timeout"]["connect"] <= 2.5
        for request in requests:
            assert request.headers["Host"] == "discord.com"
            assert request.extensions["sni_hostname"] == "discord.com"
            assert request.headers["X-GoA2-Event-ID"] == "event"

    asyncio.run(run())


def test_all_addresses_fail_before_retrying_resolution(monkeypatch):
    async def run():
        attempted = []

        def handle(request):
            attempted.append(request.url.host)
            raise httpx.ConnectError("unreachable")

        resolver = AsyncMock(return_value=["8.8.8.8", "1.1.1.1"])
        sleep = AsyncMock()
        monkeypatch.setattr("goa2.server.webhooks.resolve_public_addresses", resolver)
        monkeypatch.setattr("goa2.server.webhooks.asyncio.sleep", sleep)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await WebhookDispatcher(client)._deliver(
                "game", WebhookConfig(**JSON_HOOK), {}, "event"
            )
        assert attempted == ["8.8.8.8", "1.1.1.1"] * 3
        assert resolver.await_count == 3
        assert sleep.await_count == 2

    asyncio.run(run())


def test_queue_order_cross_game_progress_and_shutdown(monkeypatch):
    async def run():
        gate = asyncio.Event()
        other_game = asyncio.Event()
        delivered = []
        async with httpx.AsyncClient() as client:
            dispatcher = WebhookDispatcher(client)

            async def deliver(game_id, config, payload, event_id):
                if game_id == "slow":
                    await gate.wait()
                delivered.append((game_id, payload["event_id"]))
                if game_id == "fast":
                    other_game.set()

            monkeypatch.setattr(dispatcher, "_deliver", deliver)
            for event in ("one", "two"):
                dispatcher.enqueue("slow", WebhookConfig(**JSON_HOOK), {"event_id": event})
            dispatcher.enqueue("fast", WebhookConfig(**JSON_HOOK), {"event_id": "three"})
            await asyncio.wait_for(other_game.wait(), 1)
            assert delivered == [("fast", "three")]
            gate.set()
            await asyncio.gather(*list(dispatcher.tasks.values()))
            assert delivered[1:] == [("slow", "one"), ("slow", "two")]
            gate.clear()
            dispatcher.enqueue("slow", WebhookConfig(**JSON_HOOK), {"event_id": "cancel"})
            await dispatcher.close()
            assert not dispatcher.tasks

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure", [httpx.ConnectError("secret-token"), TimeoutError("secret-token")]
)
def test_network_failure_retries_and_does_not_expose_exception(monkeypatch, caplog, failure):
    async def run():
        async with httpx.AsyncClient() as client:
            send = AsyncMock(side_effect=failure)
            monkeypatch.setattr(client, "send", send)
            monkeypatch.setattr(
                "goa2.server.webhooks.resolve_public_addresses", AsyncMock(return_value=["8.8.8.8"])
            )
            sleep = AsyncMock()
            monkeypatch.setattr("goa2.server.webhooks.asyncio.sleep", sleep)
            await WebhookDispatcher(client)._deliver(
                "game", WebhookConfig(**JSON_HOOK), {"event_id": "one"}, "one"
            )
            assert send.await_count == 3
            assert [call.args[0] for call in sleep.await_args_list] == [1.0, 2.0]

    asyncio.run(run())
    assert "exhausted retries" in caplog.text
    assert "secret-token" not in caplog.text


def test_rejected_dns_never_sends_and_queue_is_bounded(monkeypatch, caplog):
    async def run():
        async with httpx.AsyncClient() as client:
            send = AsyncMock()
            monkeypatch.setattr(client, "send", send)
            monkeypatch.setattr(
                "goa2.server.webhooks.resolve_public_addresses",
                AsyncMock(side_effect=ValueError("private")),
            )
            dispatcher = WebhookDispatcher(client)
            await dispatcher._deliver("game", WebhookConfig(**JSON_HOOK), {}, "one")
            send.assert_not_awaited()
            for index in range(101):
                dispatcher.enqueue("game", WebhookConfig(**JSON_HOOK), {"event_id": str(index)})
            assert len(dispatcher.queues["game"]) == 100
            dispatcher.cancel_game("game")
            await dispatcher.close()
            assert not dispatcher.queues

    asyncio.run(run())
    assert "queue full" in caplog.text
    assert "secret-token" not in caplog.text
