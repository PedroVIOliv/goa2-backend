"""Shared orchestration for minting replay-share artifacts."""

from __future__ import annotations

import asyncio
import threading
import weakref
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from fastapi import HTTPException

from goa2.server import shares
from goa2.server.models import ShareLinkResponse
from goa2.server.replay import load_replay
from goa2.server.share_bake import bake_replay_share
from goa2.server.shares import _share_dir
from goa2.server.workers import run_heavy

_MINT_LOCK_STRIPES = 128
_MINT_LOCKS_BY_LOOP: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, tuple[asyncio.Lock, ...]
] = weakref.WeakKeyDictionary()
_MINT_TASKS_BY_LOOP: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[str, asyncio.Task[ShareLinkResponse]]
] = weakref.WeakKeyDictionary()
_MINT_STATE_GUARD = threading.Lock()


def _mint_lock(game_id: str) -> asyncio.Lock:
    """Return a bounded event-loop-local lock stripe for one game."""
    loop = asyncio.get_running_loop()
    with _MINT_STATE_GUARD:
        locks = _MINT_LOCKS_BY_LOOP.get(loop)
        if locks is None:
            locks = tuple(asyncio.Lock() for _ in range(_MINT_LOCK_STRIPES))
            _MINT_LOCKS_BY_LOOP[loop] = locks
    return locks[hash(game_id) % _MINT_LOCK_STRIPES]


def _link(token: str) -> ShareLinkResponse:
    return ShareLinkResponse(token=token, url=f"/shared/{token}")


def _forget_mint_task(
    loop: asyncio.AbstractEventLoop,
    game_id: str,
    completed: asyncio.Task[ShareLinkResponse],
) -> None:
    """Drop only the completed task that still owns this game's slot."""
    with _MINT_STATE_GUARD:
        tasks = _MINT_TASKS_BY_LOOP.get(loop)
        if tasks is not None and tasks.get(game_id) is completed:
            del tasks[game_id]

    # A disconnected request may leave no waiter to retrieve a producer error.
    # Observing it here prevents an otherwise misleading asyncio warning; later
    # waiters can still receive the same exception from the completed task.
    if not completed.cancelled():
        completed.exception()


def _mint_task(path: Path, game_id: str) -> asyncio.Task[ShareLinkResponse]:
    """Return the one request-independent mint producer for this game."""
    loop = asyncio.get_running_loop()
    with _MINT_STATE_GUARD:
        tasks = _MINT_TASKS_BY_LOOP.get(loop)
        if tasks is None:
            tasks = {}
            _MINT_TASKS_BY_LOOP[loop] = tasks
        task = tasks.get(game_id)
        if task is None:
            task = loop.create_task(
                _mint_replay_share(path, game_id),
                name=f"mint-replay-share:{game_id}",
            )
            tasks[game_id] = task
            task.add_done_callback(lambda completed: _forget_mint_task(loop, game_id, completed))
        return task


async def _mint_replay_share(path: Path, game_id: str) -> ShareLinkResponse:
    """Validate, idempotently bake, and publish one finished replay share."""
    # The existence check and bake are one critical section. Without it, two
    # players clicking Share together can both publish an artifact.
    async with _mint_lock(game_id):
        # Normal lookup reads one durable index entry and one meta file. The
        # first lookup after upgrading may also build indexes for legacy shares,
        # so all filesystem and JSON work still stays off the event loop.
        existing = await asyncio.to_thread(shares.share_for_game, game_id)
        if existing is not None:
            return _link(existing["token"])

        if not await asyncio.to_thread(path.is_file):
            raise HTTPException(status_code=404, detail="Replay not found")
        try:
            # Validate only when a bake is needed. This avoids reparsing for an
            # idempotent hit and lets a self-contained share outlive its log.
            await asyncio.to_thread(load_replay, str(path))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            result = await run_heavy(bake_replay_share, str(path), game_id, _share_dir())
        except BrokenProcessPool as exc:
            raise HTTPException(
                status_code=500, detail="The bake process died; check server logs"
            ) from exc

        if result["ok"]:
            return _link(result["token"])

        reason = result["reason"]
        if reason == "unfinished":
            raise HTTPException(
                status_code=409,
                detail="Only finished games can be shared; this game has no winner yet",
            )
        raise HTTPException(
            status_code=422,
            detail=f"Replay reconstruction failed at decision {result['at']}: {result['error']}",
        )


async def mint_replay_share(path: Path, game_id: str) -> ShareLinkResponse:
    """Join this game's in-flight mint without giving the request ownership."""
    # Client disconnects cancel their request task. Shielding keeps that from
    # cancelling the shared producer, whose strong reference lives in the
    # per-loop registry until publication or failure is complete.
    return await asyncio.shield(_mint_task(path, game_id))
