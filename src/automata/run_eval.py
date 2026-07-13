"""CLI: run an agent evaluation and print the summary.

Usage:
    PYTHONPATH=src uv run python -m automata.run_eval --games 50 --seed 0
"""

from __future__ import annotations

import argparse

from .eval import evaluate
from .random_agent import RandomAgent

# Quick-game recommended roster (2v2, single lane).
RED = ["Wasp", "Xargatha"]
BLUE = ["Arien", "Brogan"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate GoA2 agents head-to-head.")
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    # Baseline sanity check: Random vs Random should be ~50% (sides alternate).
    result = evaluate(
        lambda s: RandomAgent(s),
        lambda s: RandomAgent(s),
        red_heroes=RED,
        blue_heroes=BLUE,
        games=args.games,
        base_seed=args.seed,
        label_a="Random",
        label_b="Random",
    )
    print(result.summary())


if __name__ == "__main__":
    main()
