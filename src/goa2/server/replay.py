"""Minimal, durable game replay logs.

A replay log captures the *least* information needed to reconstruct a game
exactly: the setup parameters (including the RNG seed) plus the ordered list of
player decisions. Because gameplay is fully deterministic given the seed, and
the only state-changing client operations are card commits, passes, and input
responses, replaying those decisions in order reproduces the game byte-for-byte.

Format: one JSON object per line (JSONL).

  line 1  setup header:
    {"v":1,"type":"setup","game_id":"...","map":"forgotten_island",
     "red":["Arien"],"blue":["Wasp"],"game_type":"QUICK","cheats":false,
     "seed":1234,"engine":"<git sha>","created_at":1718900000.0}

  line N  one decision (in applied order), tagged with round/turn:
    {"type":"commit","r":1,"t":1,"hero":"hero_arien","card":"arien_basic_1"}
    {"type":"pass","r":1,"t":1,"hero":"hero_wasp"}
    {"type":"input","r":3,"t":2,"hero":"hero_arien","sel":"minion_4"}

Replays are durable: they live in their own directory with their own
retention (default 30 days) and are NOT deleted when a game's save is removed.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from goa2.domain.input import InputResponse
from goa2.domain.types import HeroID
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup

logger = logging.getLogger(__name__)

REPLAY_VERSION = 1
DEFAULT_REPLAY_DIR = "data/replays"
DEFAULT_REPLAY_TTL_DAYS = 30


def _replay_dir() -> str:
    return os.environ.get("GOA2_REPLAY_DIR", DEFAULT_REPLAY_DIR)


def _replay_ttl_days() -> int:
    try:
        return int(os.environ.get("GOA2_REPLAY_TTL_DAYS", DEFAULT_REPLAY_TTL_DAYS))
    except ValueError:
        return DEFAULT_REPLAY_TTL_DAYS


def _resolve_map_path(map_name: str) -> str:
    """Resolve a map name to its JSON file path (mirrors routes_games._map_path)."""
    base = os.path.join(os.path.dirname(__file__), "..", "data", "maps")
    return os.path.normpath(os.path.join(base, f"{map_name}.json"))


def _engine_revision() -> str:
    """Best-effort git sha so a replay/engine mismatch is detectable. Never raises."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


class ReplayRecorder:
    """Append-only writer for a single game's replay log.

    Safe to re-create against an existing file (e.g. after a server restart):
    the setup header is written only when the file is new/empty; decisions are
    appended thereafter.
    """

    def __init__(self, game_id: str, replay_dir: str | None = None) -> None:
        self.game_id = game_id
        directory = Path(replay_dir or _replay_dir())
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{game_id}.jsonl"

    @property
    def has_setup(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def _append(self, record: dict[str, Any]) -> None:
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(record, separators=(",", ":")) + "\n")
        except OSError:
            logger.exception("Failed to append replay record for game %s", self.game_id)

    def record_setup(
        self,
        *,
        map_name: str,
        red_heroes: list[str],
        blue_heroes: list[str],
        game_type: str,
        cheats: bool,
        seed: int,
    ) -> None:
        """Write the setup header. No-op if the log already has a header."""
        if self.has_setup:
            return
        self._append(
            {
                "v": REPLAY_VERSION,
                "type": "setup",
                "game_id": self.game_id,
                "map": map_name,
                "red": red_heroes,
                "blue": blue_heroes,
                "game_type": game_type,
                "cheats": cheats,
                "seed": seed,
                "engine": _engine_revision(),
                "created_at": time.time(),
            }
        )

    def record_commit(self, hero_id: str, card_id: str, round_num: int, turn: int) -> None:
        self._append(
            {"type": "commit", "r": round_num, "t": turn, "hero": hero_id, "card": card_id}
        )

    def record_pass(self, hero_id: str, round_num: int, turn: int) -> None:
        self._append({"type": "pass", "r": round_num, "t": turn, "hero": hero_id})

    def record_input(self, hero_id: str, selection: Any, round_num: int, turn: int) -> None:
        self._append(
            {"type": "input", "r": round_num, "t": turn, "hero": hero_id, "sel": selection}
        )


def create_replay_recorder(game_id: str, replay_dir: str | None = None) -> ReplayRecorder:
    """Create a ReplayRecorder using GOA2_REPLAY_DIR (or the default) when unset."""
    return ReplayRecorder(game_id, replay_dir=replay_dir)


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------


def load_replay(path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read a replay file into (setup_header, decisions). Raises FileNotFoundError."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Replay file not found: {path}")

    setup: dict[str, Any] | None = None
    decisions: list[dict[str, Any]] = []
    with open(p) as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            record = json.loads(raw)
            if record.get("type") == "setup":
                setup = record
            else:
                decisions.append(record)

    if setup is None:
        raise ValueError(f"Replay file has no setup header: {path}")
    return setup, decisions


def replay_game(
    path: str,
    *,
    until_round: int | None = None,
    until_turn: int | None = None,
    until_decision: int | None = None,
) -> GameSession:
    """Reconstruct a game from its replay log, returning a live GameSession.

    Stop points (apply none, one, or combine):
      - until_decision=N : apply only the first N decisions.
      - until_round=R [, until_turn=T] : stop before the first decision that
        occurs at/after round R (and turn T), leaving the session positioned at
        the start of that moment — the point a bug was reported.
      - none : replay the entire game.

    The returned GameSession can be inspected (`.state`, `build_view(...)`) or
    advanced further one decision at a time.
    """
    setup, decisions = load_replay(path)

    state = GameSetup.create_game(
        _resolve_map_path(setup["map"]),
        setup["red"],
        setup["blue"],
        setup.get("cheats", False),
        setup.get("game_type", "LONG"),
        seed=setup["seed"],
    )
    session = GameSession(state)

    for i, decision in enumerate(decisions):
        if until_decision is not None and i >= until_decision:
            break
        # Stop before the first decision at/after the target round/turn, leaving
        # the session positioned at the start of that moment.
        if _decision_at_or_after(decision, until_round, until_turn):
            break
        _apply_decision(session, decision)

    return session


def _decision_at_or_after(
    decision: dict[str, Any], until_round: int | None, until_turn: int | None
) -> bool:
    if until_round is None:
        return False
    r = decision.get("r", 0)
    if r != until_round:
        return r > until_round
    if until_turn is None:
        return True
    return decision.get("t", 0) >= until_turn


def _apply_decision(session: GameSession, decision: dict[str, Any]) -> None:
    kind = decision.get("type")
    hero_id = HeroID(decision["hero"])

    if kind == "commit":
        hero = session.state.get_hero(hero_id)
        if hero is None:
            raise ValueError(f"Replay: hero {hero_id} not found for commit")
        card = next((c for c in hero.hand if c.id == decision["card"]), None)
        if card is None:
            raise ValueError(
                f"Replay: card {decision['card']} not in hand of {hero_id} "
                "(engine version mismatch?)"
            )
        session.commit_card(hero_id, card)
    elif kind == "pass":
        session.pass_turn(hero_id)
    elif kind == "input":
        session.advance(InputResponse(request_id="", selection=decision["sel"]))
    else:
        raise ValueError(f"Replay: unknown decision type {kind!r}")


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def cleanup_old_replays(replay_dir: str | None = None, ttl_days: int | None = None) -> int:
    """Delete replay files older than ttl_days (by mtime). Returns count removed.

    Independent of the game-save cleanup: a finished/removed game's replay is
    retained for the full TTL so bugs reported later can still be investigated.
    """
    directory = Path(replay_dir or _replay_dir())
    if not directory.is_dir():
        return 0
    ttl = (ttl_days if ttl_days is not None else _replay_ttl_days()) * 86400
    now = time.time()
    removed = 0
    for f in directory.glob("*.jsonl"):
        try:
            if now - f.stat().st_mtime > ttl:
                f.unlink()
                removed += 1
                logger.info("Removed stale replay %s", f.name)
        except OSError:
            logger.exception("Failed to remove stale replay %s", f)
    return removed
