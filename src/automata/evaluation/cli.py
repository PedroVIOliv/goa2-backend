"""CLI: run the agent evaluation matrix and record baselines.

The eval matrix is the yardstick the whole AI effort is judged on: every
stronger agent must beat the previous baseline over a statistically meaningful
sample (Wilson CI). This runs a set of A-vs-B matchups and prints — and
optionally writes — the results.

Usage:
    # Quick baseline (small sample), print only:
    PYTHONPATH=src uv run python -m automata.evaluation.cli --games 20

    # Full matrix, write results JSON:
    PYTHONPATH=src uv run python -m automata.evaluation.cli \\
        --games 100 --out src/automata/evaluation/baselines.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime

from ..agents.base import Agent
from ..agents.heuristic_agent import HeuristicAgent
from ..agents.random_agent import RandomAgent
from ..search import ISMCTSAgent, SearchConfig
from .matchup import MatchupResult, evaluate

# Quick-game recommended roster (2v2, single lane).
RED = ["Wasp", "Xargatha"]
BLUE = ["Arien", "Brogan"]

AgentFactory = Callable[[int], Agent]

# Named agent factories. Search agents use a small iteration budget so the
# matrix runs in reasonable time; strength tuning is a separate concern.
# NOTE: an ISMCTS *game* is expensive (~28s at 2 iters, ~160s at 16), since each
# decision runs many determinized playouts. So search matchups run at a small
# game count + low iteration budget by default; the fast (random/heuristic)
# matchups run a larger sample. Bump --games / SEARCH_ITERS for a real eval run.


def _factories(search_iters: int) -> dict[str, AgentFactory]:
    return {
        "random": lambda s: RandomAgent(s),
        "heuristic": lambda s: HeuristicAgent(s),
        "ismcts": lambda s: ISMCTSAgent(SearchConfig(iterations=search_iters, seed=s)),
        "ismcts_noprior": lambda s: ISMCTSAgent(
            SearchConfig(iterations=search_iters, seed=s, use_prior=False)
        ),
    }


# The matchups that define the ladder. Each later rung must beat the agent it
# claims to improve on here. ``search`` flags the slow (ISMCTS) matchups so the
# CLI can run them at a reduced sample.
_MATCHUPS: tuple[tuple[str, str, bool], ...] = (
    ("random", "random", False),  # sanity: ~50%
    ("heuristic", "random", False),  # heuristic must dominate random
    ("ismcts", "heuristic", True),  # search must beat its own default policy
    ("ismcts", "ismcts_noprior", True),  # does the prior help at equal budget?
)


def run_matrix(
    games: int,
    base_seed: int,
    *,
    search_games: int | None = None,
    search_iters: int = 8,
) -> list[MatchupResult]:
    """Run every matchup. Fast matchups use ``games``; slow (ISMCTS) matchups
    use ``search_games`` (default: min(games, 6)) at ``search_iters`` budget."""
    facts = _factories(search_iters)
    sg = search_games if search_games is not None else min(games, 6)
    results: list[MatchupResult] = []
    for a_name, b_name, is_search in _MATCHUPS:
        n = sg if is_search else games
        res = evaluate(
            facts[a_name],
            facts[b_name],
            red_heroes=RED,
            blue_heroes=BLUE,
            games=n,
            base_seed=base_seed,
            label_a=a_name,
            label_b=b_name,
        )
        results.append(res)
    return results


def _result_dict(r: MatchupResult) -> dict[str, object]:
    lo, hi = r.wilson_ci()
    return {
        "a": r.label_a,
        "b": r.label_b,
        "games": r.games,
        "a_wins": r.a_wins,
        "b_wins": r.b_wins,
        "draws": r.draws,
        "a_winrate": round(r.a_winrate, 4),
        "wilson_ci": [round(lo, 4), round(hi, 4)],
        "avg_rounds": round(r.avg_rounds, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GoA2 agent evaluation matrix.")
    parser.add_argument("--games", type=int, default=20, help="Games per fast matchup.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--search-games", type=int, default=None, help="Games per ISMCTS matchup."
    )
    parser.add_argument(
        "--search-iters", type=int, default=8, help="ISMCTS iterations per decision."
    )
    parser.add_argument("--out", type=str, default=None, help="Write results JSON here.")
    args = parser.parse_args()

    results = run_matrix(
        args.games,
        args.seed,
        search_games=args.search_games,
        search_iters=args.search_iters,
    )
    for r in results:
        print(r.summary())

    if args.out:
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "games": args.games,
            "search_games": args.search_games if args.search_games is not None else min(args.games, 6),
            "base_seed": args.seed,
            "search_iterations": args.search_iters,
            "red": RED,
            "blue": BLUE,
            "notes": (
                "Rung-0 baseline. Fast matchups (random/heuristic) use --games; "
                "ISMCTS matchups use a small --search-games at low --search-iters "
                "because a single ISMCTS game is expensive (~28s at 2 iters). "
                "ISMCTS rows are therefore directional (wide Wilson CI), not "
                "conclusive; rerun with higher budgets for a real strength claim. "
                "Every later rung must beat the agent it improves on in these "
                "matchups over a meaningful sample."
            ),
            "matchups": [_result_dict(r) for r in results],
        }
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"\nWrote baselines to {args.out}")


if __name__ == "__main__":
    main()
