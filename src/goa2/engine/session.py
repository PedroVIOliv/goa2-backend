"""
Game Session - Phase 2 Engine Self-Containment.

Provides a clean interface for clients to interact with the engine
without touching execution_stack or calling internal functions.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Union, Dict, Any
from pydantic import BaseModel, ConfigDict

from goa2.domain.state import GameState
from goa2.domain.models import GamePhase, Card, TeamColor
from goa2.domain.types import HeroID
from goa2.domain.input import InputRequest, InputResponse


class SessionResultType(str, Enum):
    INPUT_NEEDED = "INPUT_NEEDED"
    ACTION_COMPLETE = "ACTION_COMPLETE"
    PHASE_CHANGED = "PHASE_CHANGED"
    GAME_OVER = "GAME_OVER"


class SessionResult(BaseModel):
    result_type: SessionResultType
    input_request: Optional[InputRequest] = None
    current_phase: GamePhase
    winner: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class GameSession:
    """
    High-level orchestrator for game interactions.

    Clients interact exclusively through this class:
    - commit_card() / pass_turn() during PLANNING
    - advance() during RESOLUTION and other phases
    """

    def __init__(self, state: GameState):
        self.state = state
        self._last_phase = state.phase

    @property
    def current_phase(self) -> GamePhase:
        return self.state.phase

    def commit_card(self, hero_id: HeroID, card: Card) -> SessionResult:
        if self.state.phase != GamePhase.PLANNING:
            raise ValueError(f"Cannot commit card in {self.state.phase} phase")
        from goa2.engine.phases import commit_card as _commit_card

        _commit_card(self.state, hero_id, card)
        return self._check_after_planning()

    def pass_turn(self, hero_id: HeroID) -> SessionResult:
        if self.state.phase != GamePhase.PLANNING:
            raise ValueError(f"Cannot pass in {self.state.phase} phase")
        from goa2.engine.phases import pass_turn as _pass_turn

        _pass_turn(self.state, hero_id)
        return self._check_after_planning()

    def advance(
        self, response: Optional[Union[InputResponse, Dict[str, Any]]] = None
    ) -> SessionResult:
        if self.state.phase == GamePhase.PLANNING:
            raise ValueError(
                "Cannot advance() during PLANNING. Use commit_card() or pass_turn()."
            )
        from goa2.engine.handler import submit_input, process_stack

        if response is not None:
            submit_input(self.state, response)

        request = process_stack(self.state)
        return self._build_result(request)

    # -- internals --

    def _check_after_planning(self) -> SessionResult:
        """After a planning action, check if phase transitioned."""
        if self.state.phase != self._last_phase:
            from goa2.engine.handler import process_stack

            request = process_stack(self.state)
            result = self._build_result(request)
            self._last_phase = self.state.phase
            return result
        return SessionResult(
            result_type=SessionResultType.ACTION_COMPLETE,
            current_phase=self.state.phase,
        )

    def _build_result(
        self, request: Optional[InputRequest] = None
    ) -> SessionResult:
        if self.state.phase == GamePhase.GAME_OVER:
            return SessionResult(
                result_type=SessionResultType.GAME_OVER,
                current_phase=GamePhase.GAME_OVER,
                winner=self._determine_winner(),
            )
        if request is not None:
            return SessionResult(
                result_type=SessionResultType.INPUT_NEEDED,
                input_request=request,
                current_phase=self.state.phase,
            )
        if self.state.phase != self._last_phase:
            result = SessionResult(
                result_type=SessionResultType.PHASE_CHANGED,
                current_phase=self.state.phase,
            )
            self._last_phase = self.state.phase
            return result
        return SessionResult(
            result_type=SessionResultType.ACTION_COMPLETE,
            current_phase=self.state.phase,
        )

    def _determine_winner(self) -> Optional[str]:
        red = self.state.teams.get(TeamColor.RED)
        blue = self.state.teams.get(TeamColor.BLUE)
        if not red or not blue:
            return None
        if red.life_counters <= 0:
            return "BLUE"
        if blue.life_counters <= 0:
            return "RED"
        return None
