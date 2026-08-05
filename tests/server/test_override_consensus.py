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
