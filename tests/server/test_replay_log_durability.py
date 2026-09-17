"""The save file carries the replay log, so a crash can't leave the two disagreeing."""

from __future__ import annotations

import json
from pathlib import Path

from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.server.registry import GameRegistry
from goa2.server.replay import _resolve_map_path, load_replay

MAP = "forgotten_island"


def _create(registry: GameRegistry) -> str:
    state = GameSetup.create_game(
        _resolve_map_path(MAP), ["Arien"], ["Wasp"], False, "QUICK", seed=7
    )
    session = GameSession(state)
    hero_ids = [h.id for team in state.teams.values() for h in team.heroes]
    game = registry.create_game(session, hero_ids)
    game.replay_recorder.record_setup(
        map_name=MAP,
        red_heroes=["Arien"],
        blue_heroes=["Wasp"],
        game_type="QUICK",
        cheats=False,
        seed=7,
    )
    return game.game_id


def _commit(registry: GameRegistry, game_id: str, hero_id: str, card_id: str) -> None:
    registry.get(game_id).replay_recorder.record_commit(hero_id, card_id, 1, 1)


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _restart(save_dir: Path) -> GameRegistry:
    registry = GameRegistry(save_dir=str(save_dir))
    registry.restore_all()
    return registry


def test_save_carries_every_replay_record(tmp_path):
    registry = GameRegistry(save_dir=str(tmp_path))
    game_id = _create(registry)
    _commit(registry, game_id, "hero_arien", "card_a")
    registry.save_game(game_id)

    saved = json.loads((tmp_path / f"{game_id}.json").read_text())
    log_path = registry.get(game_id).replay_recorder.path
    assert saved["replay_log"] == _lines(log_path)
    assert [r["type"] for r in saved["replay_log"]] == ["setup", "commit"]


def test_restore_repairs_log_zeroed_by_power_loss(tmp_path):
    registry = GameRegistry(save_dir=str(tmp_path))
    game_id = _create(registry)
    _commit(registry, game_id, "hero_arien", "card_a")
    registry.save_game(game_id)
    log_path = registry.get(game_id).replay_recorder.path
    expected = _lines(log_path)

    raw = log_path.read_bytes().splitlines(keepends=True)
    log_path.write_bytes(raw[0] + b"\x00" * len(raw[1]))

    restored = _restart(tmp_path)
    assert _lines(log_path) == expected
    load_replay(str(log_path))
    _commit(restored, game_id, "hero_wasp", "card_b")
    assert [r["type"] for r in _lines(log_path)] == ["setup", "commit", "commit"]


def test_restore_repairs_log_missing_its_tail(tmp_path):
    registry = GameRegistry(save_dir=str(tmp_path))
    game_id = _create(registry)
    _commit(registry, game_id, "hero_arien", "card_a")
    registry.save_game(game_id)
    log_path = registry.get(game_id).replay_recorder.path
    expected = _lines(log_path)

    log_path.write_bytes(log_path.read_bytes().splitlines(keepends=True)[0])

    _restart(tmp_path)
    assert _lines(log_path) == expected


def test_restore_drops_decision_the_save_never_reached(tmp_path):
    registry = GameRegistry(save_dir=str(tmp_path))
    game_id = _create(registry)
    registry.save_game(game_id)
    _commit(registry, game_id, "hero_arien", "card_a")

    log_path = registry.get(game_id).replay_recorder.path
    _restart(tmp_path)
    assert [r["type"] for r in _lines(log_path)] == ["setup"]


def test_restore_keeps_unsaved_setup_and_clock_records(tmp_path):
    registry = GameRegistry(save_dir=str(tmp_path))
    game_id = _create(registry)
    registry.get(game_id).replay_recorder.record_clock("STARTED", round_num=1, turn=1)
    log_path = registry.get(game_id).replay_recorder.path
    before = _lines(log_path)

    restored = _restart(tmp_path)
    assert _lines(log_path) == before
    restored.save_game(game_id)
    saved = json.loads((tmp_path / f"{game_id}.json").read_text())
    assert saved["replay_log"] == before


def _strip_replay_log_from_save(save_dir: Path, game_id: str) -> None:
    path = save_dir / f"{game_id}.json"
    payload = json.loads(path.read_text())
    del payload["replay_log"]
    path.write_text(json.dumps(payload))


def test_legacy_save_adopts_intact_log(tmp_path):
    registry = GameRegistry(save_dir=str(tmp_path))
    game_id = _create(registry)
    _commit(registry, game_id, "hero_arien", "card_a")
    registry.save_game(game_id)
    _strip_replay_log_from_save(tmp_path, game_id)
    log_path = registry.get(game_id).replay_recorder.path

    restored = _restart(tmp_path)
    restored.save_game(game_id)
    saved = json.loads((tmp_path / f"{game_id}.json").read_text())
    assert saved["replay_log"] == _lines(log_path)


def test_legacy_save_leaves_damaged_log_unmirrored(tmp_path):
    registry = GameRegistry(save_dir=str(tmp_path))
    game_id = _create(registry)
    _commit(registry, game_id, "hero_arien", "card_a")
    registry.save_game(game_id)
    _strip_replay_log_from_save(tmp_path, game_id)
    log_path = registry.get(game_id).replay_recorder.path
    damaged = b"\x00" * 10 + log_path.read_bytes()
    log_path.write_bytes(damaged)

    restored = _restart(tmp_path)
    restored.save_game(game_id)
    saved = json.loads((tmp_path / f"{game_id}.json").read_text())
    assert "replay_log" not in saved
    assert log_path.read_bytes() == damaged
