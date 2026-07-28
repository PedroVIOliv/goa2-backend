"""Agent interface.

An Agent makes two kinds of decisions, matching the engine's two decision
points (see ENGINE_INTEGRATION.md):

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
    return option.id
