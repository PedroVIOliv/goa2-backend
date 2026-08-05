"""Headless self-play harness.

Drives a full game between agents through the engine's `GameSession`, with no
web server. Deterministic given a seed. This is both the smoke test for the
integration and the substrate the eval harness / MCTS will build on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from goa2.domain.input import InputResponse
from goa2.domain.models import GamePhase
from goa2.domain.models.unit import Hero
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.session import GameSession, SessionResultType
from goa2.engine.setup import GameSetup

from ..agents.base import Agent
from .effects import register_all_effects
from .trajectory import NullRecorder, TrajectoryRecorder

DEFAULT_MAP = str(
    Path(__file__).resolve().parents[2] / "goa2" / "data" / "maps" / "forgotten_island.json"
)


@dataclass
class RunResult:
    winner: str | None
    rounds: int
    turns: int
    steps: int
    reason: str


def _all_heroes(state: GameState) -> list[Hero]:
    heroes: list[Hero] = []
    for team in state.teams.values():
        heroes.extend(team.heroes)
    return heroes


def _team_of_request(state: GameState, player_id: str) -> str | None:
    """Team responsible for a decision addressed to ``player_id`` (best-effort)."""
    if player_id.startswith("team:"):
        return player_id.split(":", 1)[1]
    for team in state.teams.values():
        for hero in team.heroes:
            if hero.id == player_id and hero.team is not None:
                return hero.team.value
    return None


def _option_key(option: Any) -> Any:
    """JSON-safe legal-key for a request option (raw selection value)."""
    meta = getattr(option, "metadata", {}) or {}
    if "hex" in meta:
        return meta["hex"]
    if "raw" in meta:
        return meta["raw"]
    return getattr(option, "id", None)


def _agent_for(agents: Mapping[str, Agent], player_id: str, state: GameState) -> Agent:
    """Resolve the agent responsible for a decision.

    `player_id` is usually a hero id; for team-scoped decisions (e.g.
    "team:RED") we fall back to an agent controlling a hero on that team, else
    any agent.
    """
    if player_id in agents:
        return agents[player_id]
    if player_id.startswith("team:"):
        color = player_id.split(":", 1)[1]
        for team in state.teams.values():
            if team.color.value == color or team.color.name == color:
                for hero in team.heroes:
                    if hero.id in agents:
                        return agents[hero.id]
    return next(iter(agents.values()))


def run_game(
    red_heroes: list[str],
    blue_heroes: list[str],
    agents: Mapping[str, Agent],
    *,
    map_path: str = DEFAULT_MAP,
    game_type: str = "QUICK",
    seed: int = 0,
    max_steps: int = 20_000,
    recorder: TrajectoryRecorder | None = None,
) -> RunResult:
    """Play one game to completion; return the outcome.

    ``agents`` maps hero_id -> Agent. All heroes must be covered (a single agent
    instance may control several heroes).

    When ``recorder`` is given, a full state snapshot + decision context is
    emitted per decision, and the final outcome at game end (Seam 4 — self-play
    training data). Recording is off by default and perf-neutral when absent.
    """
    register_all_effects()
    rec: TrajectoryRecorder = recorder if recorder is not None else NullRecorder()
    state = GameSetup.create_game(
        map_path=map_path,
        red_heroes=red_heroes,
        blue_heroes=blue_heroes,
        game_type=game_type,
        seed=seed,
    )
    session = GameSession(state)

    steps = 0
    pending_response: InputResponse | dict[str, Any] | None = None

    while steps < max_steps:
        steps += 1

        if session.current_phase == GamePhase.PLANNING:
            # Simultaneous commit: every hero not yet committed picks a card.
            # Committing the last hero can flip the phase to RESOLUTION mid-loop
            # (e.g. when another hero was auto-passed), so re-check each time.
            for hero in _all_heroes(state):
                if session.current_phase != GamePhase.PLANNING:
                    break
                if hero.id in state.pending_inputs:
                    continue
                agent = agents.get(hero.id) or _agent_for(agents, hero.id, state)
                card = agent.choose_card(state, hero)
                if recorder is not None:
                    rec.record_decision(
                        state=state,
                        team=hero.team.value if hero.team else "",
                        decision_kind="CARD",
                        player_id=hero.id,
                        legal_keys=[c.id for c in hero.hand],
                        chosen_key=card.id if card is not None else None,
                    )
                if card is None or not hero.hand:
                    session.pass_turn(HeroID(hero.id))
                else:
                    session.commit_card(HeroID(hero.id), card)
            # Planning done for this turn; fall through to advance() next loop.
            pending_response = None
            continue

        result = session.advance(pending_response)
        pending_response = None

        if result.result_type == SessionResultType.GAME_OVER:
            rec.record_outcome(winner=result.winner, rounds=state.round, reason="game_over")
            return RunResult(
                winner=result.winner,
                rounds=state.round,
                turns=state.turn,
                steps=steps,
                reason="game_over",
            )

        if result.result_type == SessionResultType.INPUT_NEEDED:
            request = result.input_request
            assert request is not None
            agent = _agent_for(agents, request.player_id, state)
            selection = agent.choose_input(state, request)
            if recorder is not None:
                rec.record_decision(
                    state=state,
                    team=(_team_of_request(state, request.player_id) or ""),
                    decision_kind="INPUT",
                    player_id=request.player_id,
                    legal_keys=[_option_key(o) for o in request.options],
                    chosen_key=selection,
                )
            pending_response = InputResponse(request_id=request.id, selection=selection)
        # ACTION_COMPLETE / PHASE_CHANGED: just keep advancing.

    rec.record_outcome(winner=None, rounds=state.round, reason="max_steps")
    return RunResult(winner=None, rounds=state.round, turns=state.turn, steps=steps, reason="max_steps")
