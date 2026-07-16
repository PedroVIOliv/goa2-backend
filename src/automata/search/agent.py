"""ISMCTS agent: same `Agent` protocol as random/heuristic, backed by search.

Each decision the harness asks for becomes the *root* of a fresh search. The
opponent (and, during rollouts, we ourselves) are played by a `HeuristicAgent`
default policy — this is the "opponent-as-environment" first cut (B). The agent
infers its perspective team from the decision it is handed: a hero's team for a
card choice, or the addressed team for an input request.
"""

from __future__ import annotations

from typing import Any

from goa2.domain.input import InputRequest
from goa2.domain.models import TeamColor
from goa2.domain.models.card import Card
from goa2.domain.models.unit import Hero
from goa2.domain.state import GameState

from ..agents.base import Agent, option_selection_value
from ..agents.heuristic_agent import HeuristicAgent
from .config import SearchConfig
from .ismcts import _branchable, _input_raw_map, _team_of_player, search


class ISMCTSAgent:
    """Information-Set MCTS decision-maker (cut B: fixed opponent model)."""

    def __init__(
        self,
        config: SearchConfig | None = None,
        *,
        default_policy: Agent | None = None,
    ) -> None:
        self._cfg = config or SearchConfig()
        # Default policy drives opponents and rollouts. Seeded off the search
        # seed for reproducibility.
        self._policy: Agent = default_policy or HeuristicAgent(self._cfg.seed)

    # -- planning ----------------------------------------------------------- #
    def choose_card(self, state: GameState, hero: Hero) -> Card | None:
        if not hero.hand:
            return None
        our_team = hero.team or TeamColor.RED
        legal = [c.id for c in hero.hand]
        result = search(state, our_team, "CARD", legal, self._policy, self._cfg)
        if result.best_key is None:
            return None
        return next((c for c in hero.hand if c.id == result.best_key), None)

    # -- resolution --------------------------------------------------------- #
    def choose_input(self, state: GameState, request: InputRequest) -> Any:
        # Non-branchable requests (empty options, e.g. UPGRADE_PHASE) carry their
        # choices outside `options`; defer to the default policy that knows them.
        if not _branchable(request):
            return self._policy.choose_input(state, request)

        raw_map = _input_raw_map(request)
        legal = list(raw_map.keys())
        if not legal:
            return "SKIP" if request.can_skip else None

        our_team = _team_of_player(state, request.player_id) or TeamColor.RED
        result = search(state, our_team, "INPUT", legal, self._policy, self._cfg)
        if result.best_key is None:
            return (
                option_selection_value(request.options[0])
                if request.options
                else ("SKIP" if request.can_skip else None)
            )
        return raw_map[result.best_key]
