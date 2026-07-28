"""Single-perspective ISMCTS driver (cut B).

Design (see the AI layer sketch):
- **Determinization** fixes one plausible hidden world per iteration by
  resampling enemy face-down commits (`runtime.determinize`).
- **Opponents are the environment.** Every enemy decision — planning commits and
  resolution inputs — is played by a fixed *default policy* (a HeuristicAgent),
  never branched on. So every tree node is one of *our* decisions: a MAX node.
- **Depth cutoff.** A rollout stops once the round counter advances
  `cfg.cutoff_rounds` (≈ one wave), then substitutes `evaluate_state` squashed
  into [0, 1]. Terminal wins/losses map to 1.0 / 0.0 and dominate.

The engine is driven through a throwaway `GameSession` over a single clone that
is *mutated in place* as the iteration descends and rolls out — one clone per
iteration, no per-edge cloning.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from goa2.domain.input import InputRequest, InputResponse
from goa2.domain.models import GamePhase, TeamColor
from goa2.domain.models.card import Card
from goa2.domain.models.unit import Hero
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.session import GameSession, SessionResultType

from ..agents.base import Agent, option_selection_value
from ..evaluation.features import evaluate_state
from ..runtime.determinize import determinize
from .config import SearchConfig
from .node import Key, Node, action_key

# --------------------------------------------------------------------------- #
# Decision representation: what the engine is asking *us* for right now.
# --------------------------------------------------------------------------- #


@dataclass
class Decision:
    kind: str  # "CARD" | "INPUT" | "OVER"
    hero: Hero | None = None
    request: InputRequest | None = None
    winner: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.kind == "OVER"


def _enemy(team: TeamColor) -> TeamColor:
    return TeamColor.BLUE if team == TeamColor.RED else TeamColor.RED


def _team_of_player(state: GameState, player_id: str) -> TeamColor | None:
    """Team responsible for a decision addressed to `player_id`.

    `player_id` is a hero id or a team delegate like "team:RED".
    """
    if player_id.startswith("team:"):
        name = player_id.split(":", 1)[1]
        for color in state.teams:
            if color.value == name or color.name == name:
                return color
        return None
    hero = state.get_hero(HeroID(player_id))
    return hero.team if hero is not None else None


def _find_card(hero: Hero, card_id: Any) -> Card | None:
    return next((c for c in hero.hand if c.id == card_id), None)


def _input_raw_map(request: InputRequest) -> dict[Key, Any]:
    """Map each legal action key at this request back to its raw selection."""
    raw: dict[Key, Any] = {}
    for opt in request.options:
        value = option_selection_value(opt)
        raw[action_key(value)] = value
    if request.can_skip:
        raw["SKIP"] = "SKIP"
    return raw


def _branchable(request: InputRequest) -> bool:
    """Can the search meaningfully branch on this request?

    Requests whose choices are not carried in `options` — notably the
    simultaneous, legacy-shaped `UPGRADE_PHASE` (choices live in
    `context["players"]`) — are not searchable. We defer them to the default
    policy, which knows their bespoke response shape. Searching (or forcing) an
    empty-option request would otherwise loop the engine forever.
    """
    return bool(request.options)


def legal_keys(decision: Decision) -> list[Key]:
    """Legal action keys at one of *our* decisions ([] means forced / no branch)."""
    if decision.kind == "CARD":
        hero = decision.hero
        assert hero is not None
        return [c.id for c in hero.hand]  # empty hand -> forced pass, no branch
    if decision.kind == "INPUT":
        assert decision.request is not None
        return list(_input_raw_map(decision.request).keys())
    return []


class _Simulator:
    """Drives one determinized clone forward, auto-playing the opponent.

    Stops (returns a `Decision`) only on *our* decisions or game over; enemy
    planning commits and resolution inputs are resolved via the default policy.
    """

    def __init__(
        self,
        state: GameState,
        our_team: TeamColor,
        default_policy: Agent,
    ) -> None:
        self.state = state
        self.session = GameSession(state)
        self.our_team = our_team
        self.default_policy = default_policy

    # -- opponent-as-environment advance ----------------------------------- #
    def _next_uncommitted(self) -> Hero | None:
        for team in self.state.teams.values():
            for hero in team.heroes:
                if hero.id not in self.state.pending_inputs:
                    return hero
        return None

    def _is_ours(self, player_id: str) -> bool:
        return _team_of_player(self.state, player_id) == self.our_team

    def advance(self, pending: InputResponse | None = None) -> Decision:
        """Advance until the engine needs one of *our* decisions, or ends."""
        resp = pending
        while True:
            if self.state.phase == GamePhase.PLANNING:
                hero = self._next_uncommitted()
                if hero is not None:
                    if hero.team == self.our_team:
                        return Decision("CARD", hero=hero)
                    # Enemy commit = hidden sample via default policy.
                    card = self.default_policy.choose_card(self.state, hero)
                    if card is None or not hero.hand:
                        self.session.pass_turn(HeroID(hero.id))
                    else:
                        self.session.commit_card(HeroID(hero.id), card)
                    continue
                # All committed: fall through to advance the resolution stack.

            result = self.session.advance(resp)
            resp = None

            if result.result_type == SessionResultType.GAME_OVER:
                return Decision("OVER", winner=result.winner)
            if result.result_type == SessionResultType.INPUT_NEEDED:
                request = result.input_request
                assert request is not None
                if self._is_ours(request.player_id) and _branchable(request):
                    return Decision("INPUT", request=request)
                # Enemy input, or a non-branchable request (e.g. UPGRADE_PHASE):
                # resolve with the default policy and keep advancing.
                selection = self.default_policy.choose_input(self.state, request)
                resp = InputResponse(request_id=request.id, selection=selection)
                continue
            # ACTION_COMPLETE / PHASE_CHANGED: keep advancing.

    # -- applying *our* action --------------------------------------------- #
    def apply_ours(self, decision: Decision, key: Key | None) -> Decision:
        """Apply our chosen action (key=None means the forced/no-branch move)."""
        if decision.kind == "CARD":
            hero = decision.hero
            assert hero is not None
            card = _find_card(hero, key) if key is not None else None
            if card is None or not hero.hand:
                self.session.pass_turn(HeroID(hero.id))
            else:
                self.session.commit_card(HeroID(hero.id), card)
            return self.advance()

        # INPUT
        request = decision.request
        assert request is not None
        if key is None:
            selection = "SKIP" if request.can_skip else None
        else:
            selection = _input_raw_map(request).get(key, key)
        return self.advance(InputResponse(request_id=request.id, selection=selection))


# --------------------------------------------------------------------------- #
# Value estimation
# --------------------------------------------------------------------------- #


def _terminal_value(winner: str | None, our_team: TeamColor) -> float:
    if winner is None:
        return 0.5  # draw / undecided
    return 1.0 if winner.upper() == our_team.value.upper() else 0.0


def _squash(score: float, scale: float) -> float:
    """Map an unbounded evaluate_state score into (0, 1)."""
    return 0.5 * (1.0 + math.tanh(score / scale))


def _rollout(sim: _Simulator, decision: Decision, cfg: SearchConfig) -> float:
    """Default-policy playout from `decision` until the round-count cutoff."""
    start_round = sim.state.round
    while not decision.is_terminal and (sim.state.round - start_round) < cfg.cutoff_rounds:
        if decision.kind == "CARD":
            hero = decision.hero
            assert hero is not None
            card = sim.default_policy.choose_card(sim.state, hero)
            decision = sim.apply_ours(decision, card.id if card is not None else None)
        else:
            request = decision.request
            assert request is not None
            selection = sim.default_policy.choose_input(sim.state, request)
            decision = sim.advance(InputResponse(request_id=request.id, selection=selection))
    if decision.is_terminal:
        return _terminal_value(decision.winner, sim.our_team)
    return _squash(evaluate_state(sim.state, sim.our_team), cfg.value_scale)


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #


def _simulate(
    root: Node,
    root_state: GameState,
    root_decision_kind: str,
    our_team: TeamColor,
    default_policy: Agent,
    cfg: SearchConfig,
    rng: random.Random,
) -> None:
    """One ISMCTS iteration on a fresh determinized clone (mutated in place)."""
    world = determinize(root_state, our_team, rng)
    sim = _Simulator(world, our_team, default_policy)
    decision = sim.advance()  # first *our* decision in this world (the root)

    node = root
    path = [root]
    value: float | None = None

    while not decision.is_terminal:
        legal = legal_keys(decision)
        if not legal:
            # Forced move (empty hand / no options): no branch, just advance.
            decision = sim.apply_ours(decision, None)
            continue

        if node.should_expand(legal, cfg.widening_c, cfg.widening_alpha):
            key = node.expand(legal, rng)
            child = node.children[key]
            node = child
            path.append(child)
            decision = sim.apply_ours(decision, key)
            value = _rollout(sim, decision, cfg)  # evaluate freshly expanded leaf
            break

        key = node.select(legal, cfg.uct_c, rng)
        child = node.children[key]
        node = child
        path.append(child)
        decision = sim.apply_ours(decision, key)

    if value is None:
        value = _terminal_value(decision.winner, our_team)

    for n in path:
        n.update(value)


@dataclass
class SearchResult:
    root: Node
    best_key: Key | None  # None => no real choice (forced move)


def search(
    state: GameState,
    our_team: TeamColor,
    root_decision_kind: str,
    root_legal: Sequence[Key],
    default_policy: Agent,
    cfg: SearchConfig,
) -> SearchResult:
    """Run ISMCTS and return the most-visited root action (robust child)."""
    root = Node()
    if len(root_legal) <= 1:
        return SearchResult(root, root_legal[0] if root_legal else None)

    rng = random.Random(cfg.seed)
    for _ in range(cfg.iterations):
        _simulate(root, state, root_decision_kind, our_team, default_policy, cfg, rng)

    # Robust child: most-visited legal root action (ties -> highest Q).
    def rank(key: Key) -> tuple[int, float]:
        child = root.children.get(key)
        return (child.visits, child.q) if child else (0, 0.0)

    best = max(root_legal, key=rank)
    return SearchResult(root, best)
