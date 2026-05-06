from __future__ import annotations

import logging
from dataclasses import dataclass, field

import goa2.engine.step_types as _step_types  # noqa: F401 — patches model annotations
from goa2.domain.events import GameEvent
from goa2.domain.input import InputRequest, InputResponse
from goa2.domain.models import GamePhase
from goa2.domain.state import GameState
from goa2.engine.steps import FinishedExpiringEffectStep, GameStep, StepResult

logger = logging.getLogger(__name__)


@dataclass
class StackResult:
    """Bundles the result of processing the execution stack."""

    input_request: InputRequest | None = None
    events: list[GameEvent] = field(default_factory=list)


def submit_input(state: GameState, response: InputResponse | dict) -> None:
    """Validate and apply player input to the pending step on the stack."""
    if not state.execution_stack:
        raise ValueError("No pending step to receive input")

    current_step = state.execution_stack[-1]

    if isinstance(response, InputResponse):
        current_step.pending_input = {"selection": response.selection}
    else:
        current_step.pending_input = response


def process_stack(state: GameState) -> StackResult:
    """Process the execution stack, returning StackResult with events."""
    safety_counter = 0
    MAX_STEPS = 1000
    collected_events: list[GameEvent] = []

    if state.phase == GamePhase.GAME_OVER:
        return StackResult()

    while state.execution_stack:
        safety_counter += 1
        if safety_counter > MAX_STEPS:
            raise RuntimeError("Infinite Loop detected in Engine Resolution Stack")

        current_step: GameStep = state.execution_stack.pop()

        # Centralized skip check — steps no longer need to call should_skip() themselves
        if current_step.should_skip(state.execution_context):
            continue

        result: StepResult = current_step.resolve(state, state.execution_context)

        # Collect events even from aborted steps
        collected_events.extend(result.events)

        if result.abort_action:
            _clear_to_finalize(state)
            continue

        if result.requires_input:
            state.execution_stack.append(current_step)
            # Track rollback disabled: if input targets someone other than the current actor
            if (
                result.input_request
                and state.current_actor_id is not None
                and result.input_request.player_id != str(state.current_actor_id)
            ):
                state.execution_context["rollback_disabled"] = True
            return StackResult(input_request=result.input_request, events=collected_events)

        if not result.is_finished:
            state.execution_stack.append(current_step)

        if result.new_steps:
            state.execution_stack.extend(reversed(result.new_steps))

    return StackResult(events=collected_events)


def _clear_to_finalize(state: GameState):
    """
    Clears all steps from the stack until ConfirmResolutionStep or FinalizeHeroTurnStep is found.
    Stops at ConfirmResolutionStep so the player can review the abort and optionally rollback.
    """
    from goa2.engine.steps import ConfirmResolutionStep, FinalizeHeroTurnStep

    while state.execution_stack:
        step = state.execution_stack[-1]
        if isinstance(
            step, (ConfirmResolutionStep, FinalizeHeroTurnStep, FinishedExpiringEffectStep)
        ):
            break
        state.execution_stack.pop()
        logger.debug("Skipped step: %s", step.type)


def push_steps(state: GameState, steps: list[GameStep]):
    """Helper to push new steps. Note: Stack is LIFO, so we extend in REVERSE order if we want them to execute 1, 2, 3."""
    # If we want Step 1 to run first, it must be at the TOP (end of list).
    # So if we have [S1, S2, S3], we should push S3, then S2, then S1.
    state.execution_stack.extend(reversed(steps))
