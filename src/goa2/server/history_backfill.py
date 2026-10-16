"""Single-flight reconstruction of legacy prefixes, using the replay driver."""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from typing import Any

from goa2.server.live_history import HistoryUnavailable, LiveHistory, canonical_views
from goa2.server.replay import is_replay_decision, walk_replay
from goa2.server.replay_codec import GroupBuilder
from goa2.server.workers import run_heavy

logger = logging.getLogger(__name__)
_TASKS: dict[tuple[int, str], asyncio.Task] = {}


def build_history(setup: dict, decisions: list[dict]) -> LiveHistory:
    """Picklable worker entry point; no live sessions or locks cross processes."""
    history = LiveHistory()
    for count, decision, session in walk_replay(setup, decisions):
        if decision is None and setup.get("created_at") is not None:
            decision = {"ts": setup["created_at"]}
        history.capture(session, count, decision, reconstructed=True)
    return history


def _merge(prefix: LiveHistory, old: LiveHistory, reader: Any) -> LiveHistory:
    """Replay captured views, not engine decisions, over a reconstructed prefix."""
    merged = deepcopy(prefix)
    # Edits identify captures in logical raw-prefix order, even after a prior
    # backfill preserved an older audit prefix with separately allocated IDs.
    source = [old.records[edit["add"][-1]] for edit in old.edits if edit["add"]]
    cutoff = source[0]["decision_count"]
    merged.active = merged.index_at(cutoff)
    merged.edits = [edit for edit in merged.edits if edit["at"] <= cutoff]
    prefix_reader = prefix.reader()
    last_count = cutoff

    def fill_gap(until: int) -> None:
        for record in prefix.records:
            if last_count < record["decision_count"] < until:
                merged.capture_views(
                    prefix_reader.read_all(record["position_id"]),
                    record["decision_count"],
                    {
                        "type": record.get("kind"),
                        "to": record["rewind_to"],
                        "ts": record["timestamp"],
                    },
                    anchor=record["anchor"],
                    reconstructed=True,
                )

    for index, record in enumerate(source):
        if index:
            fill_gap(record["decision_count"])
        decision = {
            "type": record.get("kind") or record["correction"],
            "to": record["rewind_to"],
            "ts": record["timestamp"],
        }
        if index == 0:
            decision = {
                "type": "ov_rewind",
                "to": record["decision_count"],
                "ts": record["timestamp"],
            }
        reconstructed = record["reconstructed"]
        try:
            captured = reader.read_all(record["position_id"])
        except HistoryUnavailable:
            candidates = prefix.index_at(record["decision_count"])
            if not candidates or record["decision_count"] > prefix.raw_count:
                raise
            captured = prefix_reader.read_all(candidates[-1])
            reconstructed = True
        merged.capture_views(
            captured,
            record["decision_count"],
            decision,
            anchor=record["anchor"],
            reconstructed=reconstructed,
        )
        last_count = record["decision_count"]
    fill_gap(min(old.raw_count, prefix.raw_count) + 1)
    # Keep old audit records and allocate fresh IDs. Previously issued position
    # IDs must never acquire a different meaning after the prefix is installed.
    offset = len(old.records)
    groups = merged.reader().groups
    for group in groups:
        group["start"] += offset
        group["body"]["start"] += offset
        group.pop("file", None)
    for record in merged.records:
        record["position_id"] += offset
    merged.records = deepcopy(old.records) + merged.records
    merged.active = [i + offset for i in merged.active]
    merged.anchors = {k: v + offset for k, v in merged.anchors.items()}
    for edit in merged.edits:
        edit["add"] = [i + offset for i in edit["add"]]
    merged.groups = reader.groups + groups
    merged.builder = GroupBuilder.restore(groups[-1]["body"], copy_values=False)
    merged.directory = old.directory
    merged.last_manifest = old.last_manifest
    merged.epoch = old.epoch + 1
    merged.revision = old.revision + 1
    merged.backfill_status = "complete"
    merged.gaps = []
    return merged


async def _backfill(game: Any, registry: Any) -> None:
    try:
        async with game.lock:
            old = game.history
            recorder = game.replay_recorder
            if old is None or recorder is None or not recorder.records:
                raise ValueError("No replay log is available for backfill")
            setup = next(r for r in recorder.records if r.get("type") == "setup")
            decisions = [deepcopy(r) for r in recorder.records if is_replay_decision(r)]
            old.backfill_status = "building"
        prefix = await run_heavy(build_history, setup, decisions)
        while True:
            async with game.lock:
                old = game.history
                version = old.revision
                snapshot = deepcopy(old)
                reader = old.reader()
            merged = await run_heavy(_merge, prefix, snapshot, reader)
            async with game.lock:
                if game.history is not old or old.revision != version:
                    continue  # Reuse the prefix; merge only the newly captured tail.
                if merged.builder is None or merged.latest_views != canonical_views(game.session):
                    raise ValueError("Reconstructed history does not match the live baseline")
                if registry.get(game.game_id) is not game:
                    return
                game.history = merged
                registry.save_game(game.game_id)
                if merged.backfill_status != "complete":
                    merged.backfill_status = "unavailable"
            await _notify(game, registry)
            return
    except Exception:
        logger.exception("Live history backfill failed for %s", game.game_id)
        async with game.lock:
            if game.history is not None:
                game.history.backfill_status = "unavailable"
                registry.save_game(game.game_id)
        await _notify(game, registry)


async def _notify(game: Any, registry: Any) -> None:
    if not game.ws_connections and not game.spectator_ws_connections:
        return
    from goa2.server.ws import broadcast

    try:
        await broadcast(game, registry)
    except Exception:
        # Socket delivery cannot invalidate successfully reconstructed data.
        logger.exception("Unable to broadcast history metadata for %s", game.game_id)


async def ensure_backfill(game: Any, registry: Any) -> None:
    task = start_backfill(game, registry)
    if task is not None:
        await asyncio.shield(task)


def start_backfill(game: Any, registry: Any) -> asyncio.Task | None:
    if game.history is None or game.history.backfill_status not in ("pending", "building"):
        return None
    key = (id(registry), game.game_id)
    task = _TASKS.get(key)
    if task is None:
        task = asyncio.create_task(
            _backfill(game, registry), name=f"history-backfill:{game.game_id}"
        )
        _TASKS[key] = task

        def finished(completed: asyncio.Task) -> None:
            if _TASKS.get(key) is completed:
                del _TASKS[key]
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)
    return task


async def stop_backfills(registry: Any) -> None:
    tasks = [task for (registry_id, _), task in _TASKS.items() if registry_id == id(registry)]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
