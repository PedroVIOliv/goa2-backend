"""Heavy game operations run off the event loop, in a separate process."""

import asyncio
import concurrent.futures
import os
import time

import pytest

from goa2.server import workers
from goa2.server.workers import run_heavy, shutdown_heavy_pool


def teardown_module():
    shutdown_heavy_pool()


def test_heavy_work_runs_in_another_process():
    worker_pid = asyncio.run(run_heavy(os.getpid))
    assert worker_pid != os.getpid()


def test_event_loop_keeps_running_during_heavy_work():
    """The whole point: one game's slow work must not freeze every other game.

    While a heavy call is in flight the loop must still schedule other
    coroutines — that is what lets an unrelated game's input be read and
    answered instead of queueing behind the rewind.
    """

    async def scenario():
        heavy = asyncio.create_task(run_heavy(time.sleep, 0.5))
        ticks = 0
        while not heavy.done():
            await asyncio.sleep(0.005)
            ticks += 1
        await heavy
        return ticks

    ticks = asyncio.run(scenario())
    # A blocked loop would tick ~0 times; a free one ticks continuously.
    assert ticks > 20, f"event loop only got {ticks} slices — it was blocked"


def test_pool_is_reused_across_calls():
    async def scenario():
        return await run_heavy(os.getpid), await run_heavy(os.getpid)

    first, second = asyncio.run(scenario())
    assert first == second != os.getpid()


def test_worker_has_the_card_effect_registry_populated():
    """A spawned worker starts with an empty registry unless the initializer runs.

    Without this, a rewind would replay the match with no card effects and
    silently rebuild a wrong game.
    """
    from goa2.engine.effects import CardEffectRegistry

    effect = asyncio.run(run_heavy(CardEffectRegistry.get, "liquid_leap"))
    assert effect is not None


def test_broken_pool_is_discarded_for_the_next_heavy_call(monkeypatch):
    class BrokenExecutor(concurrent.futures.Executor):
        def __init__(self):
            self.was_shutdown = False

        def submit(self, fn, /, *args, **kwargs):
            future: concurrent.futures.Future[int] = concurrent.futures.Future()
            future.set_exception(concurrent.futures.process.BrokenProcessPool("worker died"))
            return future

        def shutdown(self, wait=True, *, cancel_futures=False):
            self.was_shutdown = True

    broken = BrokenExecutor()
    monkeypatch.setattr(workers, "_pool", broken)

    with pytest.raises(concurrent.futures.process.BrokenProcessPool):
        asyncio.run(run_heavy(os.getpid))

    assert workers._pool is None
    assert broken.was_shutdown


def test_prewarm_starts_the_workers():
    """Pre-warming pays the ~3s worker spawn at boot, not on the first rewind."""
    import time as _time

    from goa2.server.workers import prewarm_heavy_pool

    shutdown_heavy_pool()

    async def scenario():
        await prewarm_heavy_pool()
        started = _time.perf_counter()
        await run_heavy(os.getpid)
        return (_time.perf_counter() - started) * 1000

    after_prewarm_ms = asyncio.run(scenario())
    assert after_prewarm_ms < 200, f"call took {after_prewarm_ms:.0f}ms — pool was still cold"


def test_job_rejected_by_a_shutdown_pool_is_retried_on_a_fresh_one(monkeypatch):
    """A concurrent recovery must not fail an unrelated game's heavy job.

    Discarding a broken pool shuts it down, so a caller that grabbed the same
    pool but had not submitted yet gets RuntimeError from submit(). The job
    never ran, so it is retried rather than surfaced to the game.
    """

    class ShutdownExecutor(concurrent.futures.Executor):
        def __init__(self):
            self.was_shutdown = False

        def submit(self, fn, /, *args, **kwargs):
            raise RuntimeError("cannot schedule new futures after shutdown")

        def shutdown(self, wait=True, *, cancel_futures=False):
            self.was_shutdown = True

    rejected = ShutdownExecutor()
    monkeypatch.setattr(workers, "_pool", rejected)

    worker_pid = asyncio.run(run_heavy(os.getpid))

    assert worker_pid != os.getpid()
    assert rejected.was_shutdown


def test_discarding_a_pool_leaves_other_queued_jobs_alone():
    """cancel_futures would raise CancelledError in unrelated callers."""
    cancelled: list[bool] = []

    class RecordingExecutor(concurrent.futures.Executor):
        def shutdown(self, wait=True, *, cancel_futures=False):
            cancelled.append(cancel_futures)

    pool = RecordingExecutor()
    workers._pool = pool
    workers._discard_heavy_pool(pool)

    assert cancelled == [False]
    assert workers._pool is None
