"""Consensus rules: threshold snapshotting, votes, expiry-as-rejection."""

import time
from types import SimpleNamespace

import pytest

from goa2.server.overrides import (
    connected_hero_ids,
    create_proposal,
    register_vote,
)


def _fake_game(connected: list[str]):
    """Minimal ManagedGame stand-in: tokens + live ws connections."""
    player_tokens = {f"tok_{h}": h for h in [*connected, "hero_offline"]}
    ws_connections = {f"tok_{h}": object() for h in connected}
    recorder = SimpleNamespace(path="/nonexistent.jsonl")
    return SimpleNamespace(
        player_tokens=player_tokens,
        hero_to_token={h: t for t, h in player_tokens.items()},
        hero_names={},
        ws_connections=ws_connections,
        pending_override=None,
        replay_recorder=recorder,
        session=None,
    )


def test_connected_hero_ids_only_live_connections():
    game = _fake_game(["hero_a", "hero_b"])
    assert sorted(connected_hero_ids(game)) == ["hero_a", "hero_b"]


def test_create_proposal_snapshots_voters_and_auto_yes():
    game = _fake_game(["hero_a", "hero_b", "hero_c"])
    p = create_proposal(
        game,
        "hero_a",
        {"family": "patch", "op": "set_gold", "args": {"hero_id": "hero_a", "value": 5}},
    )
    assert sorted(p.eligible_voters) == ["hero_a", "hero_b", "hero_c"]
    assert p.votes == {"hero_a": True}  # proposer auto-counts yes
    assert p.threshold() == 2  # majority of 3
    assert p.outcome() is None  # not decided yet
    assert p.summary  # server-rendered
    assert p.expires_at > time.time()


def test_two_player_game_requires_both():
    game = _fake_game(["hero_a", "hero_b"])
    p = create_proposal(game, "hero_a", {"family": "unstick", "op": "abort_action", "args": {}})
    assert p.threshold() == 2
    assert p.outcome() is None
    register_vote(p, "hero_b", True)
    assert p.outcome() == "applied"


def test_majority_no_rejects_early():
    game = _fake_game(["hero_a", "hero_b", "hero_c"])
    p = create_proposal(game, "hero_a", {"family": "unstick", "op": "abort_action", "args": {}})
    register_vote(p, "hero_b", False)
    register_vote(p, "hero_c", False)
    assert p.outcome() == "rejected"


def test_vote_from_non_eligible_rejected():
    game = _fake_game(["hero_a", "hero_b"])
    p = create_proposal(game, "hero_a", {"family": "unstick", "op": "abort_action", "args": {}})
    with pytest.raises(ValueError):
        register_vote(p, "hero_offline", True)


def test_duplicate_vote_updates_not_duplicates():
    game = _fake_game(["hero_a", "hero_b", "hero_c"])
    p = create_proposal(game, "hero_a", {"family": "unstick", "op": "abort_action", "args": {}})
    register_vote(p, "hero_b", False)
    register_vote(p, "hero_b", True)
    assert p.votes["hero_b"] is True
    assert p.outcome() == "applied"


def test_unknown_op_rejected_at_proposal_time():
    game = _fake_game(["hero_a", "hero_b"])
    with pytest.raises(ValueError):
        create_proposal(game, "hero_a", {"family": "patch", "op": "nope", "args": {}})


def test_op_family_mismatch_rejected():
    game = _fake_game(["hero_a", "hero_b"])
    with pytest.raises(ValueError):
        create_proposal(game, "hero_a", {"family": "unstick", "op": "set_gold", "args": {}})


def test_invalid_args_rejected_at_proposal_time():
    game = _fake_game(["hero_a", "hero_b"])
    with pytest.raises(ValueError):
        create_proposal(
            game,
            "hero_a",
            {"family": "patch", "op": "set_gold", "args": {"hero_id": "x", "value": -3}},
        )


def test_one_open_proposal_at_a_time():
    game = _fake_game(["hero_a", "hero_b"])
    game.pending_override = object()
    with pytest.raises(ValueError):
        create_proposal(game, "hero_a", {"family": "unstick", "op": "abort_action", "args": {}})


def test_rewind_family_needs_no_op():
    game = _fake_game(["hero_a", "hero_b"])
    # 'to' range validation against the replay log happens in the ws handler
    # where the recorder path is real; here only shape validation applies.
    p = create_proposal(game, "hero_a", {"family": "rewind", "to": 3})
    assert p.family == "rewind" and p.op is None and p.to == 3


def test_reveal_player_needs_a_hero_from_this_match():
    game = _fake_game(["hero_a", "hero_b"])
    p = create_proposal(
        game, "hero_a", {"family": "reveal_player", "args": {"hero_id": "hero_offline"}}
    )
    assert p.family == "reveal_player" and p.op is None
    assert p.args == {"hero_id": "hero_offline"}
    with pytest.raises(ValueError):
        create_proposal(game, "hero_a", {"family": "reveal_player", "args": {"hero_id": "nope"}})


def test_disconnected_proposer_rejected():
    game = _fake_game(["hero_a", "hero_b"])
    with pytest.raises(ValueError):
        create_proposal(
            game, "hero_offline", {"family": "unstick", "op": "abort_action", "args": {}}
        )


# ---------------------------------------------------------------------------
# Clock pause while a proposal is open
# ---------------------------------------------------------------------------


def test_clock_pauses_while_proposal_open():
    """reconcile_game_clock deactivates all clocks when pending_override is set."""
    from goa2.domain.time_control import TimeControlConfig
    from goa2.engine.session import GameSession
    from goa2.engine.setup import GameSetup
    from goa2.server.map_paths import resolve_map_path
    from goa2.server.registry import GameRegistry
    from goa2.server.time_control import reconcile_game_clock, set_player_ready

    config = TimeControlConfig(
        planning_allowance_seconds=10,
        resolution_allowance_seconds=20,
        response_grant_seconds=15,
        initial_time_bank_seconds=30,
        time_bank_increment_seconds=5,
        max_time_bank_seconds=60,
        upgrade_allowance_seconds=10,
    )
    state = GameSetup.create_game(
        resolve_map_path("forgotten_island"),
        ["Arien"],
        ["Wasp"],
        time_control=config,
        seed=123,
    )
    session = GameSession(state)
    hero_ids = [str(hero.id) for team in state.teams.values() for hero in team.heroes]
    game = GameRegistry().create_game(session, hero_ids, game_id="override-clock-test")

    set_player_ready(game, "hero_arien", True, 0)
    set_player_ready(game, "hero_wasp", True, 0)
    clock = game.session.state.clock
    assert clock is not None and clock.active_kind is not None  # PLANNING running

    game.pending_override = object()
    reconcile_game_clock(game, 1_000)
    assert clock.active_kind is None  # paused

    game.pending_override = None
    reconcile_game_clock(game, 2_000)
    assert clock.active_kind is not None  # resumed


# ---------------------------------------------------------------------------
# WS integration
# ---------------------------------------------------------------------------

import os  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from goa2.server.app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    os.environ["GOA2_SAVE_DIR"] = str(tmp_path)
    app = create_app()
    with TestClient(app) as c:
        yield c
    os.environ.pop("GOA2_SAVE_DIR", None)


@pytest.fixture
def game_data(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
        },
    )
    return resp.json()


def _token_for(game_data, hero_id):
    for pt in game_data["player_tokens"]:
        if pt["hero_id"] == hero_id:
            return pt["token"]
    raise ValueError(hero_id)


def _drain_until(ws, msg_type):
    for _ in range(20):
        msg = ws.receive_json()
        if msg["type"] == msg_type:
            return msg
        if msg["type"] == "ERROR" and msg_type != "ERROR":
            raise AssertionError(f"got ERROR while waiting for {msg_type}: {msg}")
    raise AssertionError(f"never received {msg_type}")


def _arien_view(update):
    return next(h for h in update["view"]["teams"]["RED"]["heroes"] if h["id"] == "hero_arien")


def test_propose_vote_apply_full_cycle(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()  # initial STATE_UPDATE
        ws_w.receive_json()
        ws_a.send_json(
            {
                "type": "PROPOSE_OVERRIDE",
                "family": "patch",
                "op": "set_gold",
                "args": {"hero_id": "hero_arien", "value": 9},
            }
        )
        proposed = _drain_until(ws_a, "OVERRIDE_PROPOSED")
        assert proposed["threshold"] == 2  # 2 connected -> both must agree
        assert proposed["tally"]["yes"] == ["hero_arien"]
        assert proposed["summary"]
        pid = proposed["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")

        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})
        resolved = _drain_until(ws_w, "OVERRIDE_RESOLVED")
        assert resolved["outcome"] == "applied"
        # Every client then receives a STATE_UPDATE with the patched value.
        update = _drain_until(ws_w, "STATE_UPDATE")
        assert _arien_view(update)["gold"] == 9


def test_second_proposal_while_open_rejected(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    # Both players connected so the proposal needs a second vote and stays open.
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}"),
    ):
        ws_a.receive_json()
        ws_a.send_json(
            {"type": "PROPOSE_OVERRIDE", "family": "unstick", "op": "abort_action", "args": {}}
        )
        _drain_until(ws_a, "OVERRIDE_PROPOSED")
        ws_a.send_json(
            {"type": "PROPOSE_OVERRIDE", "family": "unstick", "op": "abort_action", "args": {}}
        )
        err = _drain_until(ws_a, "ERROR")
        assert "already open" in err["detail"]


def test_cancel_by_proposer_only(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        ws_a.send_json(
            {"type": "PROPOSE_OVERRIDE", "family": "unstick", "op": "abort_action", "args": {}}
        )
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "CANCEL_OVERRIDE", "proposal_id": pid})
        err = _drain_until(ws_w, "ERROR")
        assert "proposer" in err["detail"].lower()
        ws_a.send_json({"type": "CANCEL_OVERRIDE", "proposal_id": pid})
        resolved = _drain_until(ws_a, "OVERRIDE_RESOLVED")
        assert resolved["outcome"] == "cancelled"


def test_spectator_cannot_propose_or_vote(client, game_data):
    gid = game_data["game_id"]
    with client.websocket_connect(f"/games/{gid}/ws?token={game_data['spectator_token']}") as ws:
        ws.receive_json()
        ws.send_json(
            {"type": "PROPOSE_OVERRIDE", "family": "unstick", "op": "abort_action", "args": {}}
        )
        err = ws.receive_json()
        assert err["type"] == "ERROR"  # existing spectator guard


def test_rejected_patch_reports_structured_reason(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        # Valid arg shape, but the entity is not on the board: passes proposal
        # validation, fails at apply time.
        ws_a.send_json(
            {
                "type": "PROPOSE_OVERRIDE",
                "family": "patch",
                "op": "move_entity",
                "args": {"entity_id": "minion_999", "hex": {"q": 0, "r": 0, "s": 0}},
            }
        )
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})
        resolved = _drain_until(ws_w, "OVERRIDE_RESOLVED")
        assert resolved["outcome"] == "rejected"
        assert resolved["reason"]["code"]  # machine-readable
        assert resolved["reason"]["message"]  # human-readable


def test_vote_no_majority_rejects_without_applying(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        ws_a.send_json(
            {
                "type": "PROPOSE_OVERRIDE",
                "family": "patch",
                "op": "set_gold",
                "args": {"hero_id": "hero_arien", "value": 99},
            }
        )
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": False})
        resolved = _drain_until(ws_w, "OVERRIDE_RESOLVED")
        assert resolved["outcome"] == "rejected"
        assert "reason" not in resolved  # outvoted, not validation-rejected
        # Value unchanged.
        ws_a.send_json({"type": "GET_VIEW"})
        update = _drain_until(ws_a, "STATE_UPDATE")
        assert _arien_view(update)["gold"] != 99


def test_rewind_proposal_replaces_session(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        initial = ws_a.receive_json()
        hand_before = len(_arien_view(initial)["hand"])
        ws_w.receive_json()
        # Make one recorded decision: Arien commits a card.
        card_id = _arien_view(initial)["hand"][0]["id"]
        ws_a.send_json({"type": "COMMIT_CARD", "card_id": card_id})
        _drain_until(ws_a, "ACTION_RESULT")
        _drain_until(ws_w, "STATE_UPDATE")
        # Rewind to before it.
        ws_a.send_json({"type": "PROPOSE_OVERRIDE", "family": "rewind", "to": 0})
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})
        resolved = _drain_until(ws_w, "OVERRIDE_RESOLVED")
        assert resolved["outcome"] == "applied"
        update = _drain_until(ws_a, "STATE_UPDATE")
        arien = _arien_view(update)
        # Arien's commit was undone: card back in hand, no pending commit.
        assert len(arien["hand"]) == hand_before
        assert arien["current_turn_card"] is None


def test_rewind_out_of_range_rejected_at_proposal(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    with client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a:
        ws_a.receive_json()
        ws_a.send_json({"type": "PROPOSE_OVERRIDE", "family": "rewind", "to": 999})
        err = _drain_until(ws_a, "ERROR")
        assert "range" in err["detail"].lower()


def test_view_payload_has_no_override_state(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    with client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a:
        initial = ws_a.receive_json()
        # Override negotiation state deliberately stays off the view.
        assert "pending_override" not in initial["view"]


# ---- Consensus pause -------------------------------------------------------


def test_pause_proposal_carries_no_op():
    game = _fake_game(["hero_a", "hero_b", "hero_c"])
    p = create_proposal(game, "hero_a", {"family": "pause"})
    assert p.family == "pause"
    assert p.op is None
    assert p.args == {}
    assert p.threshold() == 2
    assert p.summary


def test_pause_proposal_rejects_a_stray_op():
    game = _fake_game(["hero_a", "hero_b"])
    with pytest.raises(ValueError):
        create_proposal(game, "hero_a", {"family": "pause", "op": "set_gold"})


@pytest.fixture
def timed_game_data(client):
    return client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "time_control": {
                "planning_allowance_seconds": 60,
                "resolution_allowance_seconds": 60,
                "response_grant_seconds": 15,
                "initial_time_bank_seconds": 30,
                "time_bank_increment_seconds": 5,
                "max_time_bank_seconds": 60,
                "upgrade_allowance_seconds": 10,
            },
        },
    ).json()


def _ready_up(ws_a, ws_w):
    """Complete the pre-match ready check so the clock is RUNNING."""
    ws_a.send_json({"type": "SET_READY", "ready": True})
    _drain_until(ws_a, "READY_UPDATED")
    ws_w.send_json({"type": "SET_READY", "ready": True})
    _drain_until(ws_w, "READY_UPDATED")


def test_agreed_pause_freezes_the_match(client, timed_game_data):
    gid = timed_game_data["game_id"]
    t_a = _token_for(timed_game_data, "hero_arien")
    t_w = _token_for(timed_game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        _ready_up(ws_a, ws_w)

        ws_a.send_json({"type": "PROPOSE_OVERRIDE", "family": "pause"})
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})
        assert _drain_until(ws_w, "OVERRIDE_RESOLVED")["outcome"] == "applied"

        clock = _drain_until(ws_w, "STATE_UPDATE")["view"]["clock"]
        assert clock["status"] == "PAUSED"
        assert clock["pause"]["requested_by"] == "hero_arien"

        # The game itself is frozen, not just the clocks.
        ws_a.send_json({"type": "COMMIT_CARD", "card_id": "arien_tidal_wave"})
        assert "paused" in _drain_until(ws_a, "ERROR")["detail"]


def test_a_minority_cannot_pause(client, timed_game_data):
    gid = timed_game_data["game_id"]
    t_a = _token_for(timed_game_data, "hero_arien")
    t_w = _token_for(timed_game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        _ready_up(ws_a, ws_w)

        ws_a.send_json({"type": "PROPOSE_OVERRIDE", "family": "pause"})
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": False})

        assert _drain_until(ws_w, "OVERRIDE_RESOLVED")["outcome"] == "rejected"
        ws_a.send_json({"type": "GET_VIEW"})
        assert _drain_until(ws_a, "STATE_UPDATE")["view"]["clock"]["status"] == "RUNNING"


def test_every_hero_must_ready_up_to_resume(client, timed_game_data):
    gid = timed_game_data["game_id"]
    t_a = _token_for(timed_game_data, "hero_arien")
    t_w = _token_for(timed_game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        _ready_up(ws_a, ws_w)
        ws_a.send_json({"type": "PROPOSE_OVERRIDE", "family": "pause"})
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})
        _drain_until(ws_w, "OVERRIDE_RESOLVED")
        _drain_until(ws_w, "STATE_UPDATE")

        ws_a.send_json({"type": "SET_READY", "ready": True})
        _drain_until(ws_a, "READY_UPDATED")
        update = _drain_until(ws_a, "STATE_UPDATE")
        assert update["view"]["clock"]["status"] == "PAUSED"
        assert update["view"]["clock"]["ready_hero_ids"] == ["hero_arien"]

        ws_w.send_json({"type": "SET_READY", "ready": True})
        _drain_until(ws_w, "READY_UPDATED")
        assert _drain_until(ws_w, "STATE_UPDATE")["view"]["clock"]["status"] == "RUNNING"


def test_no_override_may_be_proposed_while_paused(client, timed_game_data):
    gid = timed_game_data["game_id"]
    t_a = _token_for(timed_game_data, "hero_arien")
    t_w = _token_for(timed_game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        _ready_up(ws_a, ws_w)
        ws_a.send_json({"type": "PROPOSE_OVERRIDE", "family": "pause"})
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})
        _drain_until(ws_w, "OVERRIDE_RESOLVED")

        ws_a.send_json(
            {"type": "PROPOSE_OVERRIDE", "family": "unstick", "op": "abort_action", "args": {}}
        )
        assert "paused" in _drain_until(ws_a, "ERROR")["detail"]


def test_pause_is_rejected_in_an_untimed_match(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}"),
    ):
        ws_a.receive_json()
        ws_a.send_json({"type": "PROPOSE_OVERRIDE", "family": "pause"})
        assert "time control" in _drain_until(ws_a, "ERROR")["detail"]


# ---------------------------------------------------------------------------
# Sharing links
# ---------------------------------------------------------------------------


def test_spectator_token_is_readable_without_a_vote(client, game_data):
    gid = game_data["game_id"]
    resp = client.get(
        f"/games/{gid}/spectator-token",
        headers={"Authorization": f"Bearer {_token_for(game_data, 'hero_arien')}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "game_id": gid,
        "spectator_token": game_data["spectator_token"],
    }


def test_spectator_token_needs_a_token_for_this_game(client, game_data):
    gid = game_data["game_id"]
    assert client.get(f"/games/{gid}/spectator-token").status_code == 401
    assert (
        client.get(
            f"/games/{gid}/spectator-token", headers={"Authorization": "Bearer nope"}
        ).status_code
        == 401
    )


def test_agreed_reveal_sends_the_player_token_to_players_only(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
        client.websocket_connect(f"/games/{gid}/ws?token={game_data['spectator_token']}") as ws_s,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        ws_s.receive_json()
        ws_a.send_json(
            {
                "type": "PROPOSE_OVERRIDE",
                "family": "reveal_player",
                "args": {"hero_id": "hero_wasp"},
            }
        )
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        # Spectators watch the negotiation like any other proposal.
        _drain_until(ws_s, "OVERRIDE_PROPOSED")

        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})
        assert _drain_until(ws_w, "OVERRIDE_RESOLVED")["outcome"] == "applied"
        assert _drain_until(ws_a, "PLAYER_LINK_REVEALED") == {
            "type": "PLAYER_LINK_REVEALED",
            "hero_id": "hero_wasp",
            "token": t_w,
        }
        assert _drain_until(ws_w, "PLAYER_LINK_REVEALED")["token"] == t_w

        resolved = _drain_until(ws_s, "OVERRIDE_RESOLVED")
        assert resolved["outcome"] == "applied"
        ws_s.send_json({"type": "GET_VIEW"})
        follow_up = ws_s.receive_json()
        assert follow_up["type"] != "PLAYER_LINK_REVEALED"


def test_outvoted_reveal_hands_out_nothing(client, game_data):
    gid = game_data["game_id"]
    t_a = _token_for(game_data, "hero_arien")
    t_w = _token_for(game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        ws_a.send_json(
            {
                "type": "PROPOSE_OVERRIDE",
                "family": "reveal_player",
                "args": {"hero_id": "hero_wasp"},
            }
        )
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": False})
        assert _drain_until(ws_a, "OVERRIDE_RESOLVED")["outcome"] == "rejected"
        ws_a.send_json({"type": "GET_VIEW"})
        assert ws_a.receive_json()["type"] != "PLAYER_LINK_REVEALED"


def test_reveal_may_be_proposed_while_the_match_is_paused(client, timed_game_data):
    """The seat is needed precisely when a missing player has frozen the match."""
    gid = timed_game_data["game_id"]
    t_a = _token_for(timed_game_data, "hero_arien")
    t_w = _token_for(timed_game_data, "hero_wasp")
    with (
        client.websocket_connect(f"/games/{gid}/ws?token={t_a}") as ws_a,
        client.websocket_connect(f"/games/{gid}/ws?token={t_w}") as ws_w,
    ):
        ws_a.receive_json()
        ws_w.receive_json()
        _ready_up(ws_a, ws_w)
        ws_a.send_json({"type": "PROPOSE_OVERRIDE", "family": "pause"})
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})
        _drain_until(ws_w, "OVERRIDE_RESOLVED")

        ws_a.send_json(
            {
                "type": "PROPOSE_OVERRIDE",
                "family": "reveal_player",
                "args": {"hero_id": "hero_wasp"},
            }
        )
        pid = _drain_until(ws_a, "OVERRIDE_PROPOSED")["proposal_id"]
        _drain_until(ws_w, "OVERRIDE_PROPOSED")
        ws_w.send_json({"type": "VOTE_OVERRIDE", "proposal_id": pid, "approve": True})
        assert _drain_until(ws_a, "OVERRIDE_RESOLVED")["outcome"] == "applied"
        assert _drain_until(ws_a, "PLAYER_LINK_REVEALED")["token"] == t_w
        # The pause survives the reveal.
        ws_a.send_json({"type": "GET_VIEW"})
        assert _drain_until(ws_a, "STATE_UPDATE")["view"]["clock"]["status"] == "PAUSED"
