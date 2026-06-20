"""Tests for the minimal game replay log (record + reconstruct)."""

from __future__ import annotations

import json

import pytest

from goa2.domain.types import HeroID
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.server.replay import (
    ReplayRecorder,
    _resolve_map_path,
    cleanup_old_replays,
    replay_game,
)

MAP = "forgotten_island"
RED = ["Arien"]
BLUE = ["Wasp"]


def _strip_volatile(obj):
    """Drop non-deterministic instance identifiers (step_id = id(object()))."""
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k != "step_id"}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def _hero_ids(state) -> list[str]:
    return [h.id for team in state.teams.values() for h in team.heroes]


def _first_card_id(state, hero_id: str) -> str:
    hero = state.get_hero(HeroID(hero_id))
    return hero.hand[0].id


def _live_game(seed: int = 42) -> GameSession:
    state = GameSetup.create_game(_resolve_map_path(MAP), RED, BLUE, False, "QUICK", seed=seed)
    return GameSession(state)


def _record_setup(rec: ReplayRecorder, seed: int = 42) -> None:
    rec.record_setup(
        map_name=MAP,
        red_heroes=RED,
        blue_heroes=BLUE,
        game_type="QUICK",
        cheats=False,
        seed=seed,
    )


def test_record_writes_setup_header_first(tmp_path):
    rec = ReplayRecorder("g1", str(tmp_path))
    _record_setup(rec)
    lines = (tmp_path / "g1.jsonl").read_text().splitlines()
    header = json.loads(lines[0])
    assert header["type"] == "setup"
    assert header["map"] == MAP
    assert header["red"] == RED
    assert header["blue"] == BLUE
    assert header["seed"] == 42
    assert header["v"] == 1


def test_record_and_replay_roundtrip(tmp_path):
    seed = 42
    live = _live_game(seed)

    rec = ReplayRecorder("g1", str(tmp_path))
    _record_setup(rec, seed)

    for hero_id in _hero_ids(live.state):
        card_id = _first_card_id(live.state, hero_id)
        rec.record_commit(hero_id, card_id, live.state.round, live.state.turn)
        card = next(c for c in live.state.get_hero(HeroID(hero_id)).hand if c.id == card_id)
        live.commit_card(HeroID(hero_id), card)

    replayed = replay_game(str(tmp_path / "g1.jsonl"))

    assert _strip_volatile(replayed.state.model_dump(mode="json")) == _strip_volatile(
        live.state.model_dump(mode="json")
    )


def test_replay_stops_at_decision_index(tmp_path):
    """until_decision=1 applies only the first decision (one commit)."""
    live = _live_game()
    rec = ReplayRecorder("g1", str(tmp_path))
    _record_setup(rec)

    hero_ids = _hero_ids(live.state)
    for hero_id in hero_ids:
        card_id = _first_card_id(live.state, hero_id)
        rec.record_commit(hero_id, card_id, live.state.round, live.state.turn)
        card = next(c for c in live.state.get_hero(HeroID(hero_id)).hand if c.id == card_id)
        live.commit_card(HeroID(hero_id), card)

    partial = replay_game(str(tmp_path / "g1.jsonl"), until_decision=1)
    # Only the first hero has committed -> exactly one pending input recorded.
    assert len(partial.state.pending_inputs) == 1


def test_cleanup_old_replays_removes_only_stale(tmp_path):
    import os
    import time

    old = tmp_path / "old.jsonl"
    fresh = tmp_path / "fresh.jsonl"
    old.write_text('{"type":"setup"}\n')
    fresh.write_text('{"type":"setup"}\n')

    # Age the old file 31 days.
    stale = time.time() - 31 * 86400
    os.utime(old, (stale, stale))

    removed = cleanup_old_replays(str(tmp_path), ttl_days=30)
    assert removed == 1
    assert not old.exists()
    assert fresh.exists()


def test_replay_unknown_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        replay_game(str(tmp_path / "missing.jsonl"))


def _build_log(tmp_path, seed: int = 42) -> str:
    """Drive a short game while recording, returning the replay file path."""
    live = _live_game(seed)
    rec = ReplayRecorder("cli", str(tmp_path))
    _record_setup(rec, seed)
    for hero_id in _hero_ids(live.state):
        card_id = _first_card_id(live.state, hero_id)
        rec.record_commit(hero_id, card_id, live.state.round, live.state.turn)
        card = next(c for c in live.state.get_hero(HeroID(hero_id)).hand if c.id == card_id)
        live.commit_card(HeroID(hero_id), card)
    return str(tmp_path / "cli.jsonl")


def test_cli_replay_prints_summary(tmp_path, capsys):
    from goa2.scripts.replay import main

    path = _build_log(tmp_path)
    rc = main([path])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Replay:" in out
    assert "Stopped at:" in out


def test_cli_decision_stop(tmp_path, capsys):
    from goa2.scripts.replay import main

    path = _build_log(tmp_path)
    assert main([path, "--decision", "1"]) == 0


def test_cli_missing_file_returns_error(tmp_path, capsys):
    from goa2.scripts.replay import main

    rc = main([str(tmp_path / "nope.jsonl")])
    assert rc == 1
    assert "error" in capsys.readouterr().err


def test_end_to_end_record_via_server_then_replay(tmp_path, monkeypatch):
    """Play a game through the real REST server, then replay its recorded log."""
    import os

    from fastapi.testclient import TestClient

    from goa2.server.app import create_app

    monkeypatch.setenv("GOA2_SAVE_DIR", str(tmp_path / "saves"))
    replay_dir = tmp_path / "replays"
    monkeypatch.setenv("GOA2_REPLAY_DIR", str(replay_dir))

    with TestClient(create_app()) as client:
        resp = client.post(
            "/games",
            json={"map_name": MAP, "red_heroes": RED, "blue_heroes": BLUE, "game_type": "QUICK"},
        )
        assert resp.status_code == 201
        data = resp.json()
        game_id = data["game_id"]
        tokens = {pt["hero_id"]: pt["token"] for pt in data["player_tokens"]}

        registry = client.app.state.registry
        live_state = registry.get(game_id).session.state

        for hero_id, token in tokens.items():
            view = client.get(
                f"/games/{game_id}", headers={"Authorization": f"Bearer {token}"}
            ).json()
            hand = next(
                h["hand"]
                for team in view["view"]["teams"].values()
                for h in team["heroes"]
                if h["id"] == hero_id
            )
            client.post(
                f"/games/{game_id}/cards",
                json={"card_id": hand[0]["id"]},
                headers={"Authorization": f"Bearer {token}"},
            )

        replay_file = replay_dir / f"{game_id}.jsonl"
        assert replay_file.is_file()

        replayed = replay_game(str(replay_file))
        assert _strip_volatile(replayed.state.model_dump(mode="json")) == _strip_volatile(
            live_state.model_dump(mode="json")
        )

    assert os.path.exists(replay_dir)
