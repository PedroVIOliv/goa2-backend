"""Agent interface.

An Agent makes two kinds of decisions, matching the engine's two decision
points:

1. PLANNING: pick which card to commit from a hero's hand (or pass).
2. RESOLUTION: answer an `InputRequest` by choosing one of its enumerated
   `options` (or SKIP), returning the raw selection value the engine expects.

Keeping this contract engine-driven (we never reimplement legality) means the
same interface serves random, heuristic, and search (ISMCTS) agents.
"""

from __future__ import annotations

from typing import Any, Protocol

from goa2.domain.input import InputRequest
from goa2.domain.models.card import Card
from goa2.domain.models.unit import Hero
from goa2.domain.state import GameState


class Agent(Protocol):
    """A decision-maker for one or more heroes."""

    def choose_card(self, state: GameState, hero: Hero) -> Card | None:
        """Return a card from ``hero.hand`` to commit, or None to pass."""
        ...

    def choose_input(self, state: GameState, request: InputRequest) -> Any:
        """Return the raw `selection` value answering ``request``.

        Typically the raw value behind a chosen ``InputOption`` (a unit id, a
        {q,r,s} hex dict, an int, or an option id), or the ``SKIP`` sentinel.
        """
        ...


def option_selection_value(option: Any) -> Any:
    """Extract the raw engine-facing selection value from an InputOption.

    Options built via `InputOption.from_value` stash the original value under
    metadata["hex"] or metadata["raw"]; steps expect that raw value, not the
    display id. Fall back to the option id for simple string choices.
    """
    meta = getattr(option, "metadata", {}) or {}
    if "hex" in meta:
        return meta["hex"]
    if "raw" in meta:
        return meta["raw"]
    return getattr(option, "id", option)


# --------------------------------------------------------------------------- #
# Shared hex geometry. Agents receive locations in loose forms — {q,r,s} dicts
# (option metadata, entity_locations), engine Hex objects, or anything with
# .q/.r/.s — so these tolerate all of them, unlike the engine's typed
# Hex.distance. Shared here so every agent (and feature extractor) reuses one
# implementation.
# --------------------------------------------------------------------------- #

Cube = tuple[int, int, int]


def to_cube(loc: Any) -> Cube | None:
    """Coerce a loose location into cube coords ``(q, r, s)``, or None.

    Accepts a ``{q, r, s}`` dict, an engine ``Hex``, or any object exposing
    ``.q``/``.r`` (``.s`` derived if absent). Returns None for None / unparseable
    inputs.
    """
    if loc is None:
        return None
    if isinstance(loc, dict):
        dq, dr = int(loc.get("q", 0)), int(loc.get("r", 0))
        return (dq, dr, int(loc.get("s", -dq - dr)))
    aq, ar = getattr(loc, "q", None), getattr(loc, "r", None)
    if aq is None or ar is None:
        return None
    s = getattr(loc, "s", None)
    return (int(aq), int(ar), int(s if s is not None else -aq - ar))


def hex_distance(a: Any, b: Any) -> int:
    """Cube hex distance between two loose locations.

    Returns a large sentinel (99) when either side is unparseable, so callers
    can treat "unknown" as "very far" without special-casing None.
    """
    ca, cb = to_cube(a), to_cube(b)
    if ca is None or cb is None:
        return 99
    return (abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2])) // 2


class HexLike:
    """Wrap a ``{q, r, s}`` dict so ``x in zone.hexes`` works (Hex equality by
    coords). Lets agents membership-test loose hex dicts against engine zones."""

    __slots__ = ("q", "r", "s")

    def __init__(self, d: dict[str, Any]) -> None:
        self.q = d.get("q", 0)
        self.r = d.get("r", 0)
        self.s = d.get("s", d.get("q", 0) * -1 - d.get("r", 0))

    def __eq__(self, other: object) -> bool:
        return (
            getattr(other, "q", None) == self.q
            and getattr(other, "r", None) == self.r
            and getattr(other, "s", None) == self.s
        )

    def __hash__(self) -> int:
        return hash((self.q, self.r, self.s))
