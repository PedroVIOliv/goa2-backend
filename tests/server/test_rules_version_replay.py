"""Games recorded before a rules change must still rebuild after it ships."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from goa2.bootstrap import register_all_effects
from goa2.domain.input import selection_value
from goa2.domain.types import HeroID
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.server.replay import (
    ReplayRecorder,
    _resolve_map_path,
    rebuild_session_for_rewind,
    replay_game,
    verify_replay,
)

register_all_effects()

MAP = "forgotten_island"
RED = ["Ursafar"]
BLUE = ["Tali"]
SEED = 7
# Turn 2's Angry Roar re-performs Prowling Brute's Movement from Ursafar's own
# base, where Fast Travel is legal, so version 1 inserts a choice there.
URSAFAR_CARDS = ["prowling_brute", "angry_roar"]


def _strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _strip_volatile(v)
            for k, v in obj.items()
            if k not in {"step_id", "pending_request_id"}
        }
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def _dump(session: GameSession) -> Any:
    return _strip_volatile(session.state.model_dump(mode="json"))


def _choose(request: Any) -> Any:
    ids = [o.id for o in request.options]
    kind = request.request_type.value
    ursafar = request.player_id == "hero_ursafar"
    if kind == "CHOOSE_ACTION":
        for preferred in ("SKILL", "MOVEMENT") if ursafar else ("HOLD",):
            if preferred in ids:
                return preferred
        return ids[0]
    if kind == "SELECT_CARD" and "prowling_brute" in ids:
        return "prowling_brute"
    if request.can_skip:
        return "SKIP"
    return selection_value(request.options[0])


def _play_turn(session: GameSession, rec: ReplayRecorder, cards: list[str]) -> None:
    state = session.state
    result = None
    for hero_id in ("hero_ursafar", "hero_tali"):
        hero = state.get_hero(HeroID(hero_id))
        assert hero is not None
        card_id = cards.pop(0) if hero_id == "hero_ursafar" else hero.hand[0].id
        rec.record_commit(hero_id, card_id, state.round, state.turn)
        result = session.commit_card(HeroID(hero_id), next(c for c in hero.hand if c.id == card_id))
    while result is not None and result.input_request is not None:
        request = result.input_request
        selection = _choose(request)
        rec.record_input(request.player_id, selection, state.round, state.turn)
        result = session.advance({"selection": selection})


def _set_header_rules_version(path: Path, version: int | None) -> None:
    lines = path.read_text().splitlines()
    header = json.loads(lines[0])
    if version is None:
        header.pop("rules_version", None)
    else:
        header["rules_version"] = version
    path.write_text("\n".join([json.dumps(header), *lines[1:]]) + "\n")


def _pre_versioning_game(tmp_path: Path) -> tuple[GameSession, Path, int]:
    """A game played and logged by a server from before rules versioning."""
    state = GameSetup.create_game(
        _resolve_map_path(MAP), RED, BLUE, False, "QUICK", seed=SEED, rules_version=0
    )
    session = GameSession(state)
    rec = ReplayRecorder("g1", str(tmp_path))
    rec.record_setup(
        map_name=MAP, red_heroes=RED, blue_heroes=BLUE, game_type="QUICK", cheats=False, seed=SEED
    )
    cards = list(URSAFAR_CARDS)
    _play_turn(session, rec, cards)
    after_turn_one = len(rec.path.read_text().splitlines()) - 1
    _play_turn(session, rec, cards)
    _set_header_rules_version(rec.path, None)
    return session, rec.path, after_turn_one


def test_pre_versioning_log_verifies_and_rewinds(tmp_path: Path) -> None:
    live, path, _ = _pre_versioning_game(tmp_path)
    total = len(path.read_text().splitlines()) - 1

    assert verify_replay(str(path))["ok"]
    assert _dump(rebuild_session_for_rewind(str(path), total)) == _dump(live)


def test_pre_versioning_log_replays_through_an_ov_rewind(tmp_path: Path) -> None:
    live, path, after_turn_one = _pre_versioning_game(tmp_path)
    lines = path.read_text().splitlines()
    turn_two = lines[1 + after_turn_one :]
    rewind = {"type": "ov_rewind", "r": 1, "t": 2, "hero": "hero_ursafar", "to": after_turn_one}
    path.write_text("\n".join([*lines, json.dumps(rewind), *turn_two]) + "\n")

    assert verify_replay(str(path))["ok"]
    assert _dump(replay_game(str(path))) == _dump(live)


def test_the_same_log_on_new_rules_diverges(tmp_path: Path) -> None:
    live, path, _ = _pre_versioning_game(tmp_path)
    _set_header_rules_version(path, 1)

    assert _dump(replay_game(str(path))) != _dump(live)
