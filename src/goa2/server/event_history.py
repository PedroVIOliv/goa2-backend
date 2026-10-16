"""Durable event history, projected at emission time for every game viewer."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from goa2.domain.events import GameEvent
from goa2.server.visibility import events_for_viewer

if TYPE_CHECKING:
    from goa2.server.registry import ManagedGame


def _pack_projections(
    event_id: int, event_time: int, projections: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Store each distinct payload once, with the public payload at index zero.

    Only viewers whose payload differs from the public one need an index. A
    wholly public event therefore has one payload and no per-player entries.
    Compare the already-filtered payloads, not event types: even a movement or
    timeout event can carry private metadata.
    """
    payloads = [projections["spectator"]]
    viewers: dict[str, int] = {}
    for viewer, payload in projections.items():
        if viewer == "spectator":
            continue
        try:
            index = payloads.index(payload)
        except ValueError:
            index = len(payloads)
            payloads.append(payload)
        if index != 0:
            viewers[viewer] = index
    return {
        "event_id": event_id,
        "event_time": event_time,
        "payloads": payloads,
        "viewers": viewers,
    }


def compact_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upgrade saves containing the original full payload per viewer.

    Use the saved projections rather than today's game state, preserving the
    exact historical visibility boundary. The next save writes the compact form.
    """
    return [
        (
            entry
            if "payloads" in entry
            else _pack_projections(entry["event_id"], entry["event_time"], entry["viewers"])
        )
        for entry in history
    ]


def event_for_viewer(entry: dict[str, Any], for_hero_id: str | None) -> dict[str, Any]:
    """Materialize a private copy of a viewer's frozen historical payload."""
    index = entry["viewers"].get(for_hero_id, 0) if for_hero_id is not None else 0
    return deepcopy(entry["payloads"][index])


def retain_events(game: ManagedGame, events: list[GameEvent]) -> None:
    """Stamp and retain new events under game.lock, including disconnected seats.

    Timer events may also occur in a later combined SessionResult. The same
    event object keeps its ID, so retaining that result does not duplicate it.
    Times strictly increase even within a millisecond or after a clock rollback.
    """
    pending = [event for event in events if event.event_id is None]
    if not pending:
        return
    last = game.event_history[-1] if game.event_history else None
    event_id = last["event_id"] if last else 0
    event_time = last["event_time"] if last else 0
    for event in pending:
        event_id += 1
        event_time = max(time.time_ns() // 1_000_000, event_time + 1)
        event.event_id = event_id
        event.event_time = event_time

    raw = [event.model_dump(mode="json") for event in pending]
    viewers = [*game.hero_to_token, "spectator"]
    projections = {
        viewer: events_for_viewer(
            raw, game.session.state, None if viewer == "spectator" else viewer
        )
        for viewer in viewers
    }
    for index, event_payload in enumerate(raw):
        game.event_history.append(
            _pack_projections(
                event_payload["event_id"],
                event_payload["event_time"],
                {viewer: projections[viewer][index] for viewer in viewers},
            )
        )


def events_for_delivery(
    events: list[dict[str, Any]], game: ManagedGame, for_hero_id: str | None
) -> list[dict[str, Any]]:
    """Use the same frozen projection for live delivery and reconnect catch-up.

    A combined timeout/action batch may be sent after later mutations have
    changed card visibility. Never re-project an already retained event against
    that later state. Unretained events use the normal visibility boundary.
    """
    retained: list[dict[str, Any] | None] = []
    unretained: list[dict[str, Any]] = []
    for event in events:
        event_id = event.get("event_id")
        entry = (
            game.event_history[event_id - 1]
            if type(event_id) is int and 0 < event_id <= len(game.event_history)
            else None
        )
        if entry is not None and entry["event_time"] == event.get("event_time"):
            retained.append(event_for_viewer(entry, for_hero_id))
        else:
            retained.append(None)
            unretained.append(event)
    projected = (
        iter(events_for_viewer(unretained, game.session.state, for_hero_id))
        if unretained
        else iter(())
    )
    return [event if event is not None else next(projected) for event in retained]
