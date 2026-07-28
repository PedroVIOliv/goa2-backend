"""Smoke test: a full random-vs-random game runs to completion via the engine."""

from __future__ import annotations

from automata.runtime.harness import run_game
from automata.agents.random_agent import RandomAgent


def test_random_quick_game_completes() -> None:
    # Quick game, 2v2, recommended roster (Wasp, Xargatha / Arien, Brogan).
    red = ["Wasp", "Xargatha"]
    blue = ["Arien", "Brogan"]

    # One shared random agent (seeded) controls everyone; deterministic.
    agent = RandomAgent(seed=42)
    hero_ids = ["hero_wasp", "hero_xargatha", "hero_arien", "hero_brogan"]
    agents = {hid: agent for hid in hero_ids}

    result = run_game(red, blue, agents, seed=7)

    # The game should terminate with a real result, not hit the step cap.
    assert result.reason == "game_over", f"did not finish: {result}"
    assert result.winner in {"RED", "BLUE", "red", "blue"}, f"unexpected winner {result.winner!r}"
    assert result.rounds >= 1


def test_random_game_is_deterministic() -> None:
    red = ["Wasp", "Xargatha"]
    blue = ["Arien", "Brogan"]
    hero_ids = ["hero_wasp", "hero_xargatha", "hero_arien", "hero_brogan"]

    def play() -> str | None:
        agents = {hid: RandomAgent(seed=1) for hid in hero_ids}
        return run_game(red, blue, agents, seed=123).winner

    assert play() == play()
