"""Tests for extracted state features (T2).

Pin that ``evaluate_state`` equals the hand-weighted dot product of
``state_features`` (so the split is behavior-preserving) and that the feature
vector stays aligned with the weight keys — the contract learned models depend on.
"""

from __future__ import annotations

from automata.evaluation.features import (
    FEATURE_NAMES,
    FEATURE_WEIGHTS,
    WIN_SCORE,
    evaluate_state,
    feature_vector,
    state_features,
)
from automata.runtime.effects import register_all_effects
from automata.runtime.harness import DEFAULT_MAP
from goa2.domain.models import TeamColor
from goa2.engine.setup import GameSetup

RED = ["Wasp", "Xargatha"]
BLUE = ["Arien", "Brogan"]


def _state(seed: int = 0):
    register_all_effects()
    return GameSetup.create_game(DEFAULT_MAP, RED, BLUE, game_type="QUICK", seed=seed)


def test_feature_names_match_weight_keys() -> None:
    assert set(FEATURE_NAMES) == set(FEATURE_WEIGHTS)
    assert list(FEATURE_NAMES) == list(FEATURE_WEIGHTS)  # stable order


def test_feature_vector_aligns_with_names() -> None:
    st = _state()
    feats = state_features(st, TeamColor.RED)
    vec = feature_vector(st, TeamColor.RED)
    assert vec == [feats[name] for name in FEATURE_NAMES]


def test_evaluate_state_is_weighted_dot_of_features() -> None:
    # The golden contract: evaluate_state == sum(weight * feature) on non-terminal
    # states. This is what keeps the T2 split behavior-preserving.
    for seed in range(5):
        st = _state(seed)
        for team in (TeamColor.RED, TeamColor.BLUE):
            feats = state_features(st, team)
            expected = sum(FEATURE_WEIGHTS[n] * feats[n] for n in FEATURE_WEIGHTS)
            assert evaluate_state(st, team) == expected


def test_features_are_antisymmetric_between_teams() -> None:
    st = _state()
    red = state_features(st, TeamColor.RED)
    blue = state_features(st, TeamColor.BLUE)
    for name in FEATURE_NAMES:
        assert red[name] == -blue[name]


def test_terminal_states_bypass_features() -> None:
    st = _state()
    st.winner = TeamColor.RED
    assert evaluate_state(st, TeamColor.RED) == WIN_SCORE
    assert evaluate_state(st, TeamColor.BLUE) == -WIN_SCORE
