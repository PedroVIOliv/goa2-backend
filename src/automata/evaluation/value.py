"""Value function seam for the search leaf estimate.

``ValueFn`` is the interface the search calls at a rollout cutoff: given a
non-terminal state and the perspective team, return an unbounded scalar score
(higher = better for that team). ``ismcts`` squashes it into (0, 1).

Today the only implementation is :class:`HeuristicValue`, wrapping the
hand-weighted :func:`evaluate_state`. A learned value model (Rung 2) becomes a
new implementation of this same protocol — trained on recorded trajectories
(Seam 4) over the extracted features (Seam 2) — and drops in without touching
the search loop.
"""

from __future__ import annotations

from typing import Protocol

from goa2.domain.models import TeamColor
from goa2.domain.state import GameState

from .features import evaluate_state


class ValueFn(Protocol):
    """Estimate a state's value from ``team``'s perspective (higher = better)."""

    def __call__(self, state: GameState, team: TeamColor) -> float: ...


class HeuristicValue:
    """Hand-weighted linear value (delegates to :func:`evaluate_state`)."""

    def __call__(self, state: GameState, team: TeamColor) -> float:
        return evaluate_state(state, team)
