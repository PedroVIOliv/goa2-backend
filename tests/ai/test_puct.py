"""Tests for PUCT selection (Rung 1).

The prior's weights bias tree selection (AlphaZero-style), not just expansion
order. These assert PUCT prefers high-prior children, falls back to UCB1 when
disabled or when no priors are present, and that weight normalization behaves.
"""

from __future__ import annotations

import random

from automata.search.ismcts import _normalize_weights
from automata.search.node import Node


def _child(node: Node, key: str, visits: int, total: float) -> None:
    c = Node(visits=visits, total_value=total)
    node.children[key] = c


# --- weight normalization -------------------------------------------------- #


def test_normalize_weights_is_a_distribution() -> None:
    legal = ["a", "b", "c"]
    probs = _normalize_weights({"a": 10.0, "b": 6.0, "c": 3.0}, legal)
    assert probs is not None
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    # Higher raw score -> higher probability.
    assert probs["a"] > probs["b"] > probs["c"]


def test_normalize_weights_handles_negative_scores() -> None:
    legal = ["a", "b"]
    probs = _normalize_weights({"a": -3.0, "b": -8.0}, legal)
    assert probs is not None
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    assert probs["a"] > probs["b"]


def test_normalize_weights_none_when_empty() -> None:
    assert _normalize_weights(None, ["a"]) is None
    assert _normalize_weights({}, ["a"]) is None


# --- PUCT selection --------------------------------------------------------- #


def test_puct_prefers_high_prior_child_when_q_equal() -> None:
    # Two expanded children with equal Q and equal visits: PUCT must pick the
    # one with the higher prior probability.
    node = Node(visits=10, total_value=5.0)
    _child(node, "hi", visits=2, total=1.0)  # q = 0.5
    _child(node, "lo", visits=2, total=1.0)  # q = 0.5
    legal = ["hi", "lo"]
    priors = {"hi": 0.9, "lo": 0.1}
    rng = random.Random(0)
    picks = {node.select(legal, 1.4, rng, priors, puct_c=1.5) for _ in range(5)}
    assert picks == {"hi"}


def test_puct_can_be_outweighed_by_q() -> None:
    # A clearly better Q should win despite a lower prior.
    node = Node(visits=50, total_value=25.0)
    _child(node, "good", visits=10, total=9.0)  # q = 0.9
    _child(node, "prior", visits=10, total=1.0)  # q = 0.1
    legal = ["good", "prior"]
    priors = {"good": 0.2, "prior": 0.8}
    rng = random.Random(0)
    assert node.select(legal, 1.4, rng, priors, puct_c=1.5) == "good"


def test_falls_back_to_ucb_without_priors() -> None:
    # No priors -> UCB1: an unvisited expanded child is inf -> selected first.
    node = Node(visits=10, total_value=5.0)
    _child(node, "seen", visits=5, total=2.5)
    _child(node, "fresh", visits=0, total=0.0)
    rng = random.Random(0)
    assert node.select(["seen", "fresh"], 1.4, rng, None, 0.0) == "fresh"


def test_puct_c_zero_uses_ucb() -> None:
    # puct_c = 0 disables PUCT even if priors are supplied.
    node = Node(visits=10, total_value=5.0)
    _child(node, "seen", visits=5, total=2.5)
    _child(node, "fresh", visits=0, total=0.0)
    rng = random.Random(0)
    got = node.select(["seen", "fresh"], 1.4, rng, {"seen": 0.9, "fresh": 0.1}, puct_c=0.0)
    assert got == "fresh"  # UCB1 still forces the unvisited child


def test_puct_selection_is_deterministic() -> None:
    node = Node(visits=20, total_value=10.0)
    _child(node, "a", visits=4, total=2.0)
    _child(node, "b", visits=6, total=3.6)
    legal = ["a", "b"]
    priors = {"a": 0.5, "b": 0.5}
    a = node.select(legal, 1.4, random.Random(3), priors, 1.5)
    b = node.select(legal, 1.4, random.Random(3), priors, 1.5)
    assert a == b
