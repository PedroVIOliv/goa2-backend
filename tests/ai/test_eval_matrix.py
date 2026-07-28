"""Tests for the evaluation matrix CLI (T5).

Kept cheap: exercises the fast (random/heuristic) matchups only via a tiny
sample, plus the result-dict serialization. The ISMCTS matchups are covered by
their own tests and are too slow for a unit test.
"""

from __future__ import annotations

from automata.evaluation.cli import _result_dict, run_matrix
from automata.runtime.effects import register_all_effects


def test_run_matrix_runs_all_matchups() -> None:
    register_all_effects()
    # 2 fast games, 1 ISMCTS game at the minimum iteration budget to stay quick.
    results = run_matrix(games=2, base_seed=0, search_games=1, search_iters=2)
    assert len(results) == 4
    labels = [(r.label_a, r.label_b) for r in results]
    assert ("random", "random") in labels
    assert ("heuristic", "random") in labels


def test_result_dict_is_json_serializable() -> None:
    import json

    register_all_effects()
    results = run_matrix(games=2, base_seed=0, search_games=1, search_iters=2)
    for r in results:
        d = _result_dict(r)
        # Round-trips and carries the key fields a baseline consumer expects.
        restored = json.loads(json.dumps(d))
        assert set(restored) >= {"a", "b", "games", "a_winrate", "wilson_ci"}
        assert 0.0 <= restored["a_winrate"] <= 1.0
        lo, hi = restored["wilson_ci"]
        assert 0.0 <= lo <= hi <= 1.0
