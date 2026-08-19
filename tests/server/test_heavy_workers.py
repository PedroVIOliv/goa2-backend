"""Heavy game operations run off the event loop, in a separate process."""

import asyncio
import os
import time

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
