"""Search configuration for the ISMCTS agent.

One knob-bag shared by the driver (`ismcts.py`) and the agent wrapper
(`agent.py`). Defaults are deliberately conservative so a single decision stays
in the low-hundreds-of-ms range on the ~3.4 ms clone cost.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    # How many determinized playouts per decision. Rung-1 tuning (sweep vs the
    # heuristic baseline, 24 games/config): win-rate rises monotonically
    # 8→87.5%, 16→95.8%, 32→100%. The old default (200) was untuned and
    # impractically slow with no measured benefit over 32. 32 is the top of the
    # validated range and decisively beats the heuristic.
    iterations: int = 32

    # UCB1 exploration constant. Rewards are in [0, 1], so ~1.4 (≈√2) is sane.
    # Sweep found uct_c ∈ {1.0, 1.4, 2.0} indistinguishable (prior-ordered
    # expansion dominates), so this is left at the textbook value.
    uct_c: float = 1.4

    # Depth cutoff: stop a rollout once the round counter has advanced this many
    # times, then substitute the value function. Sweep found cutoff_rounds ∈
    # {1, 2, 3} indistinguishable vs the heuristic; 1 is cheapest per rollout.
    cutoff_rounds: int = 1

    # Hard ply cap on a rollout: stop after this many of *our* decisions even if
    # the round cutoff hasn't been reached, then substitute the value function.
    # Engine step-processing dominates rollout cost, so bounding decisions
    # directly caps that cost (a round can contain many decisions/inputs). 0
    # disables the cap (round cutoff only). Sweep: cap=6 dipped to 87.5% (too
    # aggressive), cap ∈ {8, 12} held ~96–100% at ~2x less cost than uncapped.
    # 12 is the strength-neutral sweet spot.
    rollout_max_plies: int = 12

    # Progressive widening: a node with visit count N may reveal at most

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

    # PUCT selection: when > 0 and a prior is present, bias tree selection by
    # the prior probability P(a) (AlphaZero-style) instead of plain UCB1. The
    # prior is also used for expansion ordering regardless. 0 disables PUCT
    # (pure UCB1 selection).
    #
    # DEFAULT OFF: measured 2-10 (16.7%) vs plain UCB1 at 8 iters / 12 games.
    # At low iteration budgets a strong prior over-commits and under-explores,
    # while UCB1's force-try-every-child does better. PUCT stays available as a
    # knob for higher-budget / learned-policy experiments (revisit at Rung 3),
    # where a trained P(a) should make it pay off. See docs/plan_ai_ladder.md.
    puct_c: float = 0.0
