"""
Game Event System - Phase 3 of Client-Readiness Roadmap.

Structured event stream so clients can animate actions, show logs,
and build replays. Events are ephemeral by-products of step resolution,
NOT part of GameState.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from goa2.domain.hex import Hex


class GameEventType(str, Enum):
    # Movement
    UNIT_MOVED = "UNIT_MOVED"
    UNIT_PLACED = "UNIT_PLACED"
    UNIT_PUSHED = "UNIT_PUSHED"
    UNITS_SWAPPED = "UNITS_SWAPPED"
    # Combat
    COMBAT_RESOLVED = "COMBAT_RESOLVED"
    UNIT_DEFEATED = "UNIT_DEFEATED"
    UNIT_REMOVED = "UNIT_REMOVED"
    # Effects / Markers
    EFFECT_CREATED = "EFFECT_CREATED"
    MARKER_PLACED = "MARKER_PLACED"
    MARKER_REMOVED = "MARKER_REMOVED"
    # Economy
    GOLD_GAINED = "GOLD_GAINED"
    LIFE_COUNTER_CHANGED = "LIFE_COUNTER_CHANGED"
    # Cards
    CARD_RETRIEVED = "CARD_RETRIEVED"
    # Turn flow
    TURN_ENDED = "TURN_ENDED"
    GAME_OVER = "GAME_OVER"


def _hex_dict(h: Optional[Hex]) -> Optional[Dict[str, int]]:
    """Serialize a Hex to a {q, r, s} dict for JSON compatibility."""
    if h is None:
        return None
    return {"q": h.q, "r": h.r, "s": h.s}


class GameEvent(BaseModel):
    """A single game event emitted by a step during resolution."""

    event_type: GameEventType
    actor_id: Optional[str] = None
    target_id: Optional[str] = None
    from_hex: Optional[Dict[str, int]] = None
    to_hex: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
