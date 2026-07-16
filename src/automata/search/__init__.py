"""Search: Information-Set MCTS agent for the GoA2 engine.

Cut B — opponents are folded into a fixed default policy and their hidden
commits into `determinize`, so the tree is single-perspective (all MAX nodes).
Rollouts truncate at a round-count cutoff and defer to `evaluate_state`.
"""

from .agent import ISMCTSAgent
from .config import SearchConfig

__all__ = ["ISMCTSAgent", "SearchConfig"]
