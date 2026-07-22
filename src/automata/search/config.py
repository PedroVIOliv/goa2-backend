"""Search configuration for the ISMCTS agent.

One knob-bag shared by the driver (`ismcts.py`) and the agent wrapper
(`agent.py`). Defaults are deliberately conservative so a single decision stays
in the low-hundreds-of-ms range on the ~3.4 ms clone cost.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    # How many determinized playouts per decision.
    iterations: int = 200

    # UCB1 exploration constant. Rewards are in [0, 1], so ~1.4 (≈√2) is sane.
    uct_c: float = 1.4

    # Depth cutoff: stop a rollout once the round counter has advanced this many
    # times (2 ≈ one full wave resolved), then substitute the value function.
    cutoff_rounds: int = 2

    # Progressive widening: a node with visit count N may reveal at most
    # ⌈C · N^alpha⌉ children. Tames wide positioning nodes (many legal hexes).
    widening_c: float = 2.0
    widening_alpha: float = 0.5

    # evaluate_state is unbounded; squash through tanh(score / scale) into
    # (0, 1). Scale is order-of-magnitude of a meaningful positional edge.
    value_scale: float = 300.0

    # RNG seed for determinization + tie-breaking (reproducible searches).
    seed: int = 0

    # Use a heuristic expansion prior (reveal promising moves first under
    # progressive widening). Disable to fall back to random expansion order.
    use_prior: bool = True
