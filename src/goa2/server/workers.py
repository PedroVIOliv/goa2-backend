"""Off-loop execution for game operations that take seconds rather than millis.

The server runs one event loop for every game, so a synchronous multi-second
call (a consensus rewind replays a match from its log) freezes *all* tables,
not just the one that asked for it. Such work runs in a separate process
instead, which keeps the loop free to read sockets and leaves other games on
their own core rather than contending for the GIL.

Only genuinely heavy work belongs here. Shipping a GameState to a worker and
back costs ~90ms, so an ordinary mutation (~17ms of engine) is cheaper to run
inline; the win only appears when the work dwarfs the transfer.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any, TypeVar

T = TypeVar("T")

_pool: ProcessPoolExecutor | None = None
_pool_guard = threading.Lock()


def _init_worker() -> None:
    """Populate the card-effect registry in a fresh worker.

    Registration is an import side effect, so a forked worker inherits it but
    a spawned one starts empty and would rebuild a session with no effects.
    """
    from goa2.server.app import register_all_effects

    register_all_effects()


def _max_workers() -> int:
    # Three, not four: share bakes hold a worker for tens of seconds on a long
    # game, and two concurrent mints must not leave a consensus rewind queued
    # behind them. The fourth core stays free for the event loop, which serves
    # every live table.
    return int(os.environ.get("GOA2_HEAVY_WORKERS", "3"))


def get_heavy_pool() -> ProcessPoolExecutor:
    """The shared pool, created on first use.

    Bounded on purpose: concurrent heavy operations queue behind each other
    instead of spawning a process per request. "spawn" avoids forking a
    process that already has threads running.
    """
    global _pool
    with _pool_guard:
        if _pool is None:
            _pool = ProcessPoolExecutor(
                max_workers=_max_workers(),
                mp_context=multiprocessing.get_context("spawn"),
                initializer=_init_worker,
            )
        return _pool


def _discard_heavy_pool(failed_pool: ProcessPoolExecutor) -> None:
    """Forget a broken cached pool without clobbering a newer replacement."""
    global _pool
    with _pool_guard:
        if _pool is not failed_pool:
            return
        _pool = None
    # Queued jobs belong to other games. Cancelling them raises CancelledError
    # in their callers, which nothing upstream handles; letting the broken pool
    # fail them yields BrokenProcessPool, which callers already expect.
    failed_pool.shutdown(wait=False)


async def run_heavy(fn: Callable[..., T], *args: Any) -> T:
    """Run ``fn(*args)`` in a worker process, awaiting the result.

    ``fn`` and its arguments and result must all be picklable.
    """
    loop = asyncio.get_running_loop()
    pool = get_heavy_pool()
    try:
        return await loop.run_in_executor(pool, fn, *args)
    except BrokenProcessPool:
        # ProcessPoolExecutor remains permanently broken after a worker dies.
        # Drop only the failed instance so the next heavy job can create a
        # fresh pool; a concurrent recovery may already have done so.
        _discard_heavy_pool(pool)
        raise
    except RuntimeError:
        # Another caller discarded this pool between get_heavy_pool() and the
        # submit above, so Executor.submit rejects the job. Nothing ran, which
        # is what makes retrying safe here and not under BrokenProcessPool —
        # there, the job itself may be what killed the worker.
        _discard_heavy_pool(pool)
        return await loop.run_in_executor(get_heavy_pool(), fn, *args)


async def prewarm_heavy_pool() -> None:
    """Start the workers before anyone needs them.

    A worker costs seconds to spawn and import the engine, and the pool only
    starts one when work arrives — so without this the very first rewind pays
    that on top of its own runtime. One trivial job per worker forces them up.
    """
    await asyncio.gather(*(run_heavy(os.getpid) for _ in range(_max_workers())))


def shutdown_heavy_pool() -> None:
    global _pool
    with _pool_guard:
        pool = _pool
        _pool = None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)
