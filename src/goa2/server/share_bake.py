"""Out-of-process bake driver for replay shares.

Baking a share re-simulates an entire game (measured on the deployment target:
~18 ms per decision, so ~13 s for a 700-decision game). That work is pure Python
and holds the GIL, so running it in the server process — whether inline or on a
background thread, which shares the same GIL — stalls the event loop that serves
live games over WebSocket.

So the bake runs in a **separate process** through the server's bounded shared
heavy-work pool. The request still waits for it, which keeps the API simple (no
pending state, no polling, and "is this game finished?" is still answered before
responding), but the interpreter serving live games is free the whole time.

``bake_replay_share`` is the child entry point: it must be a module-level
function taking only picklable arguments, because the pool uses the ``spawn``
start method. Spawn is chosen deliberately over fork — forking a process that
already has a threadpool running is a well-known source of deadlocks.
"""

from __future__ import annotations

from typing import Any

__all__ = ["BakeResult", "bake_replay_share"]

# What the child hands back. Plain data so it survives pickling, and so engine
# exceptions never have to cross the process boundary as objects.
BakeResult = dict[str, Any]


def bake_replay_share(replay_path: str, game_id: str, share_dir: str) -> BakeResult:
    """Reconstruct a replay and bake every position. Runs in a child process.

    Rewinds are collapsed away first, so indices in the baked artifact address
    the effective timeline and do not line up with raw log indices.

    Returns one of:
      {"ok": True, "token": "..."}                     baked and published
      {"ok": False, "reason": "unfinished"}            game has no winner yet
      {"ok": False, "reason": "drift", "at": N, "error": "..."}   reconstruction failed

    """
    # A spawned child is a fresh interpreter: effects are registered as an import
    # side effect and must be re-registered here or every card resolves to nothing.
    from goa2.server.app import register_all_effects

    register_all_effects()

    from goa2.server import shares
    from goa2.server.replay import (
        _apply_decision,
        build_session_from_setup,
        effective_decisions,
        load_replay,
        state_body,
        winner_of,
    )

    setup, raw = load_replay(replay_path)
    # A share is the game as it ended. Collapsing rewinds here yields a linear
    # timeline the forward walk below can bake, and never simulates a decision
    # the table voted away.
    decisions = effective_decisions(raw)
    session = build_session_from_setup(setup)
    applied = 0

    def render(index: int) -> dict[str, Any]:
        nonlocal applied
        # bake_share renders 0..len(decisions) in order, so a single forward walk
        # suffices; no position is ever rebuilt from the seed.
        while applied < index:
            _apply_decision(session, decisions[applied])
            applied += 1
        return state_body(session, cursor_index=index, total=len(decisions))

    try:
        token = shares.bake_share(
            game_id=game_id,
            setup=setup,
            decisions=decisions,
            render=render,
            # Only known once every decision is applied, so it gates publication
            # rather than gating the walk.
            validate=lambda: winner_of(session.state) is not None,
            share_dir=share_dir,
        )
    except Exception as e:
        # Any failure to reconstruct is the same answer to the caller: this log
        # cannot be baked, and here is how far it got. Catching broadly matters
        # because a malformed record raises KeyError rather than the ValueError
        # engine drift produces, and an uncaught one would surface as a 500.
        return {
            "ok": False,
            "reason": "drift",
            "at": applied,
            "error": f"{type(e).__name__}: {e}" if not isinstance(e, ValueError) else str(e),
        }

    if token is None:
        return {"ok": False, "reason": "unfinished"}
    return {"ok": True, "token": token}
