"""Tests for the ValueFn seam (T1).

Assert HeuristicValue is behavior-identical to evaluate_state, that a custom
ValueFn is actually consulted by search, and that injection preserves
determinism.
"""

from __future__ import annotations

from automata.evaluation.features import evaluate_state
from automata.evaluation.value import HeuristicValue, ValueFn
from automata.runtime.effects import register_all_effects
from automata.runtime.harness import DEFAULT_MAP
from automata.search import ISMCTSAgent, SearchConfig
from goa2.domain.models import TeamColor
from goa2.domain.state import GameState
from goa2.engine.setup import GameSetup

RED = ["Wasp", "Xargatha"]
BLUE = ["Arien", "Brogan"]


def _state(seed: int = 2) -> GameState:
    register_all_effects()
    return GameSetup.create_game(DEFAULT_MAP, RED, BLUE, game_type="QUICK", seed=seed)


def _tiny(*, seed: int = 0) -> SearchConfig:
    return SearchConfig(iterations=4, cutoff_rounds=1, seed=seed)


def test_heuristic_value_matches_evaluate_state() -> None:
    st = _state()
    hv = HeuristicValue()
    for team in (TeamColor.RED, TeamColor.BLUE):
        assert hv(st, team) == evaluate_state(st, team)


def test_custom_value_fn_is_consulted() -> None:
    st = _state()
    calls: list[TeamColor] = []

    class SpyValue:
        def __call__(self, state: GameState, team: TeamColor) -> float:
            calls.append(team)
            return 0.0

    spy: ValueFn = SpyValue()
    agent = ISMCTSAgent(_tiny(seed=1), value_fn=spy)
    hero = st.teams[next(iter(st.teams))].heroes[0]
    agent.choose_card(st, hero)
    # With a non-trivial hand and a cutoff, the search must reach leaves and
    # call the value fn at least once.
    if len(hero.hand) > 1:
        assert calls, "custom ValueFn was never consulted by search"


def test_injected_value_fn_preserves_determinism() -> None:
    def choose() -> object:
        st = _state()
        agent = ISMCTSAgent(_tiny(seed=7), value_fn=HeuristicValue())
        hero = st.teams[next(iter(st.teams))].heroes[0]
        c = agent.choose_card(st, hero)
        return c.id if c else None

    assert choose() == choose()


def test_default_value_fn_is_heuristic() -> None:
    agent = ISMCTSAgent(_tiny())
    assert isinstance(agent._value, HeuristicValue)
