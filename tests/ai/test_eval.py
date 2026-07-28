"""Tests for the evaluation harness."""

from __future__ import annotations

from automata.evaluation.matchup import MatchupResult, evaluate
from automata.agents.random_agent import RandomAgent

RED = ["Wasp", "Xargatha"]
BLUE = ["Arien", "Brogan"]


def test_evaluate_runs_and_aggregates() -> None:
    result = evaluate(
        lambda s: RandomAgent(s),
        lambda s: RandomAgent(s),
        red_heroes=RED,
        blue_heroes=BLUE,
        games=6,
        base_seed=0,
    )
    assert result.games == 6
    assert result.a_wins + result.b_wins + result.draws == 6
    assert 0.0 <= result.a_winrate <= 1.0
    lo, hi = result.wilson_ci()
    assert 0.0 <= lo <= hi <= 1.0


def test_evaluate_is_deterministic() -> None:
    def run() -> tuple[int, int, int]:
        r = evaluate(
            lambda s: RandomAgent(s),
            lambda s: RandomAgent(s),
            red_heroes=RED,
            blue_heroes=BLUE,
            games=6,
            base_seed=99,
        )
        return (r.a_wins, r.b_wins, r.draws)

    assert run() == run()


def test_wilson_ci_bounds() -> None:
    # All A wins over a small sample -> high but not certain lower bound.
    r = MatchupResult("A", "B", games=10, a_wins=10, b_wins=0, draws=0, avg_rounds=3.0)
    lo, hi = r.wilson_ci()
    assert hi == 1.0
    assert 0.6 < lo < 1.0
    assert r.a_winrate == 1.0
