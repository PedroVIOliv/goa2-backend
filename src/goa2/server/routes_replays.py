"""Read-only replay-debugger endpoints (omniscient view).

These endpoints reconstruct *recorded* games from their on-disk `.jsonl` logs and
serve an omniscient view (`build_view(reveal_all=True)`) so a developer can step
through a game decision-by-decision to investigate a bug. They never touch the
live games in the registry.

SECURITY: because the view reveals every hand and facedown card, this router is
only registered when the `GOA2_REPLAY_API` env flag is truthy (see
server/app.py). When unset — the default, including production — the endpoints
simply do not exist (404), so omniscient data can never be served from a
deployed server. The flag is the *only* gate; no request value reaches
`reveal_all`, which is hard-coded `True` here.
"""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from goa2.domain.views import build_view
from goa2.server.replay import (
    ReplayCursor,
    _replay_dir,
    index_for_round_turn,
    load_replay,
)

router = APIRouter(prefix="/replays", tags=["replays"])


def replay_api_enabled() -> bool:
    """True when GOA2_REPLAY_API is set to a truthy value."""
    return os.environ.get("GOA2_REPLAY_API", "").strip().lower() in ("1", "true", "yes", "on")


# Tiny in-process LRU of reconstructed cursors. This is a single-user dev tool,
# so it is a plain dict with no concurrency hardening; it is a pure optimization
# (identical inputs always yield identical views).
_CACHE: OrderedDict[str, ReplayCursor] = OrderedDict()
_CACHE_MAX = 8


def _replay_path(game_id: str) -> Path:
    """Resolve a game_id to its replay file, rejecting path traversal."""
    if not game_id or "/" in game_id or "\\" in game_id or game_id.startswith("."):
        raise HTTPException(status_code=404, detail="Replay not found")
    path = Path(_replay_dir()) / f"{game_id}.jsonl"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Replay '{game_id}' not found")
    return path


def _get_cursor(game_id: str) -> ReplayCursor:
    """Return a cached ReplayCursor for the game, loading it if necessary."""
    cached = _CACHE.get(game_id)
    if cached is not None:
        _CACHE.move_to_end(game_id)
        return cached
    path = _replay_path(game_id)
    setup, decisions = load_replay(str(path))
    cursor = ReplayCursor(setup, decisions)
    _CACHE[game_id] = cursor
    _CACHE.move_to_end(game_id)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return cursor


@router.get("")
def list_replays() -> list[dict[str, Any]]:
    """List available replays (newest first) from their setup headers."""
    directory = Path(_replay_dir())
    out: list[dict[str, Any]] = []
    if not directory.is_dir():
        return out
    for f in directory.glob("*.jsonl"):
        try:
            with open(f) as fh:
                first = fh.readline()
                num_decisions = sum(1 for line in fh if line.strip())
            header = json.loads(first)
        except (OSError, json.JSONDecodeError):
            continue
        if header.get("type") != "setup":
            continue
        out.append(
            {
                "game_id": header.get("game_id", f.stem),
                "map": header.get("map"),
                "red": header.get("red", []),
                "blue": header.get("blue", []),
                "game_type": header.get("game_type"),
                "cheats": header.get("cheats", False),
                "seed": header.get("seed"),
                "engine": header.get("engine"),
                "created_at": header.get("created_at"),
                "num_decisions": num_decisions,
            }
        )
    out.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
    return out


@router.get("/{game_id}")
def get_replay_meta(game_id: str) -> dict[str, Any]:
    """Return the setup header plus the full ordered decision list for a replay."""
    path = _replay_path(game_id)
    try:
        setup, decisions = load_replay(str(path))
    except ValueError as e:  # malformed log (e.g. no setup header)
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        "setup": setup,
        "decisions": [
            {
                "index": i,
                "type": d.get("type"),
                "r": d.get("r"),
                "t": d.get("t"),
                "hero": d.get("hero"),
                "card": d.get("card"),
                "sel": d.get("sel"),
            }
            for i, d in enumerate(decisions)
        ],
    }


@router.get("/{game_id}/state")
def get_replay_state(
    game_id: str,
    decision: int | None = Query(None, description="Apply exactly N decisions"),
    round: int | None = Query(None, description="Position at the start of round R"),
    turn: int | None = Query(None, description="With round: position at turn T"),
) -> dict[str, Any]:
    """Reconstruct the game to a position and return the omniscient view.

    Position is chosen by, in priority order: `decision` (apply N decisions),
    else `round`/`turn` (start of that moment), else the end of the game.
    """
    cursor = _get_cursor(game_id)
    if decision is not None:
        target = decision
    elif round is not None:
        target = index_for_round_turn(cursor.decisions, round, turn)
    else:
        target = cursor.total
    target = max(0, min(target, cursor.total))

    try:
        session = cursor.seek(target)
    except ValueError as e:
        # Engine/replay drift (e.g. a recorded card no longer in hand). Surface
        # it: compare the header's `engine` sha to the current engine.
        raise HTTPException(
            status_code=422, detail=f"Replay reconstruction failed at decision {cursor.cursor}: {e}"
        ) from e

    state = session.state
    winner = state.winner.value if state.winner else None
    return {
        "view": build_view(state, reveal_all=True),
        "position": {
            "decision_index": cursor.cursor,
            "round": state.round,
            "turn": state.turn,
            "total_decisions": cursor.total,
        },
        "winner": winner,
    }
