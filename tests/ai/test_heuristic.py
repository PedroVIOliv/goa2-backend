"""Tests for the heuristic agent and state evaluation.

Note: we deliberately do NOT assert the heuristic beats random. Empirically the
greedy one-ply static heuristic is ~random-strength in aggregate (it wins some
games decisively and loses others) — one-ply scoring without lookahead is not
reliably better in this imperfect-information game. Its value here is (a) a
non-trivial rollout policy and (b) exercising `evaluate_state`, which MCTS needs.
"""

from __future__ import annotations

from automata.agents.heuristic_agent import HeuristicAgent
from automata.agents.random_agent import RandomAgent
from automata.evaluation.features import evaluate_state
from automata.evaluation.matchup import evaluate
from automata.runtime.effects import register_all_effects
from automata.runtime.harness import DEFAULT_MAP
from goa2.domain.models import TeamColor
from goa2.engine.setup import GameSetup


def test_evaluate_state_symmetry_and_terminal() -> None:
    register_all_effects()
    st = GameSetup.create_game(
        DEFAULT_MAP, ["Wasp", "Xargatha"], ["Arien", "Brogan"], game_type="QUICK", seed=1
    )
    # Fresh symmetric game: neither side favoured.
    assert evaluate_state(st, TeamColor.RED) == -evaluate_state(st, TeamColor.BLUE)
    assert abs(evaluate_state(st, TeamColor.RED)) < 1.0

    # Draining an enemy's life should strictly favour us.
    st.teams[TeamColor.BLUE].life_counters -= 2
    assert evaluate_state(st, TeamColor.RED) > 0
    assert evaluate_state(st, TeamColor.BLUE) < 0


def test_heuristic_game_is_deterministic() -> None:
    red = ["Wasp", "Xargatha"]
    blue = ["Arien", "Brogan"]

    def run() -> tuple[int, int]:
        r = evaluate(
            lambda s: HeuristicAgent(s),
            lambda s: RandomAgent(s),
            red_heroes=red,
            blue_heroes=blue,
            games=4,
            base_seed=0,
        )
        return (r.a_wins, r.b_wins)

    assert run() == run()


def test_heuristic_completes_games() -> None:
    r = evaluate(
        lambda s: HeuristicAgent(s),
        lambda s: RandomAgent(s),
        red_heroes=["Wasp", "Xargatha"],
        blue_heroes=["Arien", "Brogan"],
        games=4,
        base_seed=5,
    )
    # Every game resolves to a winner (no step-cap draws on this map).
    assert r.draws == 0
    assert r.a_wins + r.b_wins == 4
