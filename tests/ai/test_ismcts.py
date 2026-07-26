"""Tests for the ISMCTS search agent (cut B: fixed opponent model).

Kept deliberately cheap (tiny iteration budgets, capped games). We assert the
search is a well-formed, deterministic, legal-move agent that drives the engine
forward without stalling — not that it is strong (strength tuning is a separate,
much slower eval run).
"""

from __future__ import annotations

from automata.agents.base import Agent
from automata.agents.heuristic_agent import HeuristicAgent
from automata.runtime.effects import register_all_effects
from automata.runtime.harness import DEFAULT_MAP, run_game
from automata.search import ISMCTSAgent, SearchConfig
from goa2.engine.setup import GameSetup

RED = ["Wasp", "Xargatha"]
BLUE = ["Arien", "Brogan"]


def _tiny_cfg(seed: int = 0) -> SearchConfig:
    return SearchConfig(iterations=2, cutoff_rounds=1, seed=seed)


def _agents(agent: Agent, opp: Agent) -> dict[str, Agent]:
    return {
        "hero_wasp": agent,
        "hero_xargatha": agent,
        "hero_arien": opp,
        "hero_brogan": opp,
    }


def test_search_returns_legal_card() -> None:
    register_all_effects()
    state = GameSetup.create_game(DEFAULT_MAP, RED, BLUE, game_type="QUICK", seed=2)
    agent = ISMCTSAgent(_tiny_cfg())
    hero = state.teams[next(iter(state.teams))].heroes[0]
    card = agent.choose_card(state, hero)
    if hero.hand:
        assert card is not None
        assert card.id in {c.id for c in hero.hand}
    else:
        assert card is None


def test_rollout_ply_cap_still_returns_legal_card() -> None:
    # A capped rollout (rollout_max_plies) must still yield a legal, valid move.
    register_all_effects()
    state = GameSetup.create_game(DEFAULT_MAP, RED, BLUE, game_type="QUICK", seed=2)
    cfg = SearchConfig(iterations=4, cutoff_rounds=2, seed=0, rollout_max_plies=3)
    agent = ISMCTSAgent(cfg)
    hero = state.teams[next(iter(state.teams))].heroes[0]
    card = agent.choose_card(state, hero)
    if hero.hand:
        assert card is not None
        assert card.id in {c.id for c in hero.hand}


def test_rollout_ply_cap_is_deterministic() -> None:
    register_all_effects()

    def choose() -> object:
        state = GameSetup.create_game(DEFAULT_MAP, RED, BLUE, game_type="QUICK", seed=2)
        cfg = SearchConfig(iterations=4, cutoff_rounds=2, seed=7, rollout_max_plies=4)
        agent = ISMCTSAgent(cfg)
        hero = state.teams[next(iter(state.teams))].heroes[0]
        c = agent.choose_card(state, hero)
        return c.id if c else None

    assert choose() == choose()


def test_ismcts_progresses_without_stalling() -> None:
    register_all_effects()
    agents = _agents(ISMCTSAgent(_tiny_cfg()), HeuristicAgent(1))
    # Capped run: the fix for the UPGRADE_PHASE loop means rounds must advance.
    r = run_game(RED, BLUE, agents, seed=3, max_steps=300)
    assert r.rounds >= 3  # would be stuck at <=2 if the engine were looping


def test_ismcts_is_deterministic() -> None:
    register_all_effects()

    def run() -> tuple[str | None, int, int]:
        agents = _agents(ISMCTSAgent(_tiny_cfg(seed=7)), HeuristicAgent(1))
        r = run_game(RED, BLUE, agents, seed=5, max_steps=300)
        return (r.winner, r.rounds, r.steps)

    assert run() == run()


def test_ismcts_sustains_progress_over_long_horizon() -> None:
    register_all_effects()
    # One ISMCTS hero vs an otherwise-heuristic table. Over a long-ish capped
    # horizon the game must keep advancing (many rounds) and, if it ends, end
    # cleanly via game_over — proving no mid-game input loop. Natural
    # time-to-finish under weak search play is an eval concern, not a unit test.
    opp = HeuristicAgent(1)
    agents: dict[str, Agent] = {
        "hero_wasp": ISMCTSAgent(_tiny_cfg()),
        "hero_xargatha": opp,
        "hero_arien": opp,
        "hero_brogan": opp,
    }
    r = run_game(RED, BLUE, agents, seed=3, max_steps=1200)
    assert r.reason in ("game_over", "max_steps")
    assert r.rounds >= 8
