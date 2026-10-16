"""Durable event history, projected at emission time for every game viewer."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from goa2.domain.events import GameEvent
from goa2.server.registry import ManagedGame
from goa2.server.visibility import events_for_viewer


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
    for index, event in enumerate(pending):
        game.event_history.append(
            {
                "event_id": event.event_id,
                "event_time": event.event_time,
                "viewers": {viewer: projections[viewer][index] for viewer in viewers},
            }
        )


def events_for_delivery(
    events: list[dict[str, Any]], game: ManagedGame, for_hero_id: str | None
) -> list[dict[str, Any]]:
    """Use the same frozen projection for live delivery and reconnect catch-up.

    A combined timeout/action batch may be sent after later mutations have
    changed card visibility. Never re-project an already retained event against
    that later state. Unretained events use the normal visibility boundary.
    """
    viewer = for_hero_id if for_hero_id is not None else "spectator"
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
            retained.append(entry["viewers"][viewer])
        else:
            retained.append(None)
            unretained.append(event)
    projected = (
        iter(events_for_viewer(unretained, game.session.state, for_hero_id))
        if unretained
        else iter(())
    )
    return [deepcopy(event) if event is not None else next(projected) for event in retained]
