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
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

_pool: ProcessPoolExecutor | None = None


def _init_worker() -> None:
    """Populate the card-effect registry in a fresh worker.

    Registration is an import side effect, so a forked worker inherits it but
    a spawned one starts empty and would rebuild a session with no effects.
    """
    from goa2.server.app import register_all_effects

    register_all_effects()


def get_heavy_pool() -> ProcessPoolExecutor:
    """The shared pool, created on first use.

    Bounded on purpose: concurrent heavy operations queue behind each other
    instead of spawning a process per request. "spawn" avoids forking a
    process that already has threads running.
    """
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(
            max_workers=int(os.environ.get("GOA2_HEAVY_WORKERS", "2")),
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_init_worker,
        )
    return _pool


async def run_heavy(fn: Callable[..., T], *args: Any) -> T:
    """Run ``fn(*args)`` in a worker process, awaiting the result.

    ``fn`` and its arguments and result must all be picklable.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(get_heavy_pool(), fn, *args)


def shutdown_heavy_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
