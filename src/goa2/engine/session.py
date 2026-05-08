"""
Game Session - Phase 2 Engine Self-Containment.

Provides a clean interface for clients to interact with the engine
without touching execution_stack or calling internal functions.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from goa2.domain.events import GameEvent
from goa2.domain.input import InputRequest, InputResponse
from goa2.domain.models import Card, GamePhase, TeamColor
from goa2.domain.state import GameState
from goa2.domain.types import HeroID


class SessionResultType(StrEnum):
    INPUT_NEEDED = "INPUT_NEEDED"
    ACTION_COMPLETE = "ACTION_COMPLETE"
    PHASE_CHANGED = "PHASE_CHANGED"
    GAME_OVER = "GAME_OVER"


class SessionResult(BaseModel):
    result_type: SessionResultType
    input_request: InputRequest | None = None
    current_phase: GamePhase
    winner: str | None = None
    events: list[GameEvent] = Field(default_factory=list)

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
        self._rollback_snapshot: dict | None = None
        self._rollback_actor_id: str | None = None

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

    def advance(self, response: InputResponse | dict[str, Any] | None = None) -> SessionResult:
        if self.state.phase == GamePhase.PLANNING:
            raise ValueError("Cannot advance() during PLANNING. Use commit_card() or pass_turn().")
        from goa2.engine.handler import process_stack, submit_input

        if response is not None:
            submit_input(self.state, response)

        stack_result = process_stack(self.state)

        # Snapshot & rollback flag management
        self._manage_rollback(stack_result)

        return self._build_result(stack_result.input_request, events=stack_result.events)

    def rollback(self) -> SessionResult:
        """Rollback to the snapshot taken at the start of the current actor's resolution."""
        if self._rollback_snapshot is None:
            raise ValueError("No rollback snapshot available")

        self.state = GameState.model_validate(self._rollback_snapshot)
        # Don't clear snapshot — player may rollback again after re-choosing

        from goa2.engine.handler import process_stack

        stack_result = process_stack(self.state)
        # After restore, the first input is the action choice again
        if stack_result.input_request:
            stack_result.input_request.can_rollback = True
        return self._build_result(stack_result.input_request, events=stack_result.events)

    # -- internals --

    def _manage_rollback(self, stack_result) -> None:
        """Take snapshots and set can_rollback flag on input requests."""
        # Clear snapshot when no actor (turn ended without next actor)
        if self.state.current_actor_id is None:
            self._rollback_snapshot = None
            self._rollback_actor_id = None
            return

        if stack_result.input_request is None:
            return

        actor_id = str(self.state.current_actor_id)
        rollback_disabled = self.state.execution_context.get("rollback_disabled", False)

        if rollback_disabled:
            self._rollback_snapshot = None
            self._rollback_actor_id = None
            return

        # If actor changed, clear old snapshot so a fresh one is taken
        if self._rollback_actor_id is not None and self._rollback_actor_id != actor_id:
            self._rollback_snapshot = None
            self._rollback_actor_id = None

        # Take snapshot on the first input request targeting the current actor
        if self._rollback_snapshot is None and stack_result.input_request.player_id == actor_id:
            self._rollback_snapshot = self.state.model_dump(mode="json")
            self._rollback_actor_id = actor_id

        # Set can_rollback flag when applicable
        if self._rollback_snapshot is not None and stack_result.input_request.player_id == actor_id:
            stack_result.input_request.can_rollback = True

    def _check_after_planning(self) -> SessionResult:
        """After a planning action, check if phase transitioned."""
        if self.state.phase != self._last_phase:
            from goa2.engine.handler import process_stack

            stack_result = process_stack(self.state)
            self._manage_rollback(stack_result)
            result = self._build_result(stack_result.input_request, events=stack_result.events)
            self._last_phase = self.state.phase
            return result
        return SessionResult(
            result_type=SessionResultType.ACTION_COMPLETE,
            current_phase=self.state.phase,
        )

    def _build_result(
        self,
        request: InputRequest | None = None,
        events: list[GameEvent] | None = None,
    ) -> SessionResult:
        ev = events or []
        if self.state.phase == GamePhase.GAME_OVER:
            return SessionResult(
                result_type=SessionResultType.GAME_OVER,
                current_phase=GamePhase.GAME_OVER,
                winner=self._determine_winner(),
                events=ev,
            )
        if request is not None:
            return SessionResult(
                result_type=SessionResultType.INPUT_NEEDED,
                input_request=request,
                current_phase=self.state.phase,
                events=ev,
            )
        if self.state.phase != self._last_phase:
            result = SessionResult(
                result_type=SessionResultType.PHASE_CHANGED,
                current_phase=self.state.phase,
                events=ev,
            )
            self._last_phase = self.state.phase
            return result
        return SessionResult(
            result_type=SessionResultType.ACTION_COMPLETE,
            current_phase=self.state.phase,
            events=ev,
        )

    def _determine_winner(self) -> str | None:
        # Authoritative: TriggerGameOverStep sets state.winner for all victory types
        if self.state.winner is not None:
            return self.state.winner.value

        # Fallback: life counter check (annihilation)
        red = self.state.teams.get(TeamColor.RED)
        blue = self.state.teams.get(TeamColor.BLUE)
        if not red or not blue:
            return None
        if red.life_counters <= 0:
            return "BLUE"
        if blue.life_counters <= 0:
            return "RED"
        return None
