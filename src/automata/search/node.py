"""Tree node + selection policy for single-perspective ISMCTS.

Because opponents are folded into a fixed default policy (cut B) and their
hidden commits into `determinize`, every node in this tree is one of *our*
decisions — a pure MAX node. So a node needs only visit/value totals and a
selection rule combining UCB1 with progressive widening.

Actions are stored under a hashable *key* (see `action_key`); the raw
engine-facing value (a card id, a {q,r,s} hex dict, an int, "SKIP", …) is
reconstructed at apply-time from the live decision context, which keeps the tree
free of un-hashable payloads and information-set-consistent across
determinizations.
"""

from __future__ import annotations

import math
import random
from collections.abc import Hashable
from dataclasses import dataclass, field
from typing import Any

# Canonical action key type.
Key = Hashable


def action_key(selection: Any) -> Key:
    """Canonical hashable key for a raw engine selection value."""
    if isinstance(selection, dict):
        # Hex (or similar) dict — key by sorted coordinate tuple.
        if {"q", "r"} <= selection.keys():
            q, r = selection.get("q"), selection.get("r")
            return ("hex", q, r, selection.get("s", -(q or 0) - (r or 0)))
        return ("dict", tuple(sorted((str(k), str(v)) for k, v in selection.items())))
    if isinstance(selection, Hashable):
        return selection
    return ("repr", repr(selection))


@dataclass
class Node:
    """A single MAX decision node in the search tree."""

    visits: int = 0
    total_value: float = 0.0  # summed rollout value (our perspective), in [0, 1]
    children: dict[Key, Node] = field(default_factory=dict)

    @property
    def q(self) -> float:
        return self.total_value / self.visits if self.visits else 0.0

    def update(self, value: float) -> None:
        self.visits += 1
        self.total_value += value

    def select(self, legal: list[Key], cfg_uct_c: float, rng: random.Random) -> Key:
        """Pick a *previously expanded* legal action by UCB1.

        Callers must only invoke this when `should_expand` is False, i.e. there
        is at least one expanded legal child.
        """
        expanded = [k for k in legal if k in self.children]
        log_n = math.log(self.visits + 1)

        def ucb(k: Key) -> float:
            child = self.children[k]
            if child.visits == 0:
                return math.inf
            return child.q + cfg_uct_c * math.sqrt(log_n / child.visits)

        best = max(ucb(k) for k in expanded)
        # Break ties randomly for unbiased exploration.
        top = [k for k in expanded if ucb(k) == best]
        return rng.choice(top)

    def should_expand(self, legal: list[Key], widen_c: float, widen_alpha: float) -> bool:
        """Progressive widening gate: may we reveal a new child now?"""
        unexpanded = [k for k in legal if k not in self.children]
        if not unexpanded:
            return False
        expanded = [k for k in legal if k in self.children]
        limit = max(1, math.ceil(widen_c * (self.visits**widen_alpha)))
        return len(expanded) < limit

    def expand(
        self,
        legal: list[Key],
        rng: random.Random,
        order: list[Key] | None = None,
    ) -> Key:
        """Reveal one new legal child and return its key.

        When ``order`` (a best-first ranking of the legal keys, e.g. from an
        expansion prior) is given, reveal the highest-ranked *unexpanded* key so
        progressive widening surfaces promising moves first. Otherwise the
        ordering is random. Either way this only affects *which* legal child is
        revealed next, never legality or value.
        """
        unexpanded = {k for k in legal if k not in self.children}
        if order is not None:
            key = next((k for k in order if k in unexpanded), None)
            if key is None:  # order missing some legal keys; fall back
                key = rng.choice([k for k in legal if k in unexpanded])
        else:
            key = rng.choice([k for k in legal if k in unexpanded])
        self.children[key] = Node()
        return key
