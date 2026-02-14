from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Union

from goa2.domain.state import GameState
from goa2.domain.models import GamePhase
from goa2.domain.input import InputRequest, InputResponse
from goa2.domain.events import GameEvent
from goa2.engine.steps import GameStep, StepResult
import goa2.engine.step_types as _step_types  # noqa: F401 — patches model annotations


@dataclass
class StackResult:
    """Bundles the result of processing the execution stack."""

    input_request: Optional[InputRequest] = None
    events: List[GameEvent] = field(default_factory=list)


def submit_input(
    state: GameState, response: Union[InputResponse, dict]
) -> None:
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
    collected_events: List[GameEvent] = []

    if state.phase == GamePhase.GAME_OVER:
        return StackResult()

    while state.execution_stack:
        safety_counter += 1
        if safety_counter > MAX_STEPS:
            raise RuntimeError("Infinite Loop detected in Engine Resolution Stack")

        current_step: GameStep = state.execution_stack.pop()
        result: StepResult = current_step.resolve(state, state.execution_context)

        # Collect events even from aborted steps
        collected_events.extend(result.events)

        if result.abort_action:
            _clear_to_finalize(state)
            continue

        if result.requires_input:
            state.execution_stack.append(current_step)
            return StackResult(
                input_request=result.input_request, events=collected_events
            )

        if not result.is_finished:
            state.execution_stack.append(current_step)

        if result.new_steps:
            state.execution_stack.extend(reversed(result.new_steps))

    return StackResult(events=collected_events)


# Module-level pending events for legacy callers
_pending_events: List[GameEvent] = []


def get_pending_events() -> List[GameEvent]:
    """Return and clear pending events from the last process_resolution_stack call."""
    global _pending_events
    events = _pending_events
    _pending_events = []
    return events


def process_resolution_stack(state: GameState) -> Optional[Dict[str, Any]]:
    """
    Main Engine Loop for the Step-Based System.

    Returns a dict representation of InputRequest for backwards compatibility.
    The internal steps now use typed InputRequest models.
    """
    global _pending_events

    safety_counter = 0
    MAX_STEPS = 1000
    collected_events: List[GameEvent] = []

    if state.phase == GamePhase.GAME_OVER:
        print("   [ENGINE] Game is Over. Halting execution.")
        _pending_events = collected_events
        return None

    while state.execution_stack:
        safety_counter += 1
        if safety_counter > MAX_STEPS:
            raise RuntimeError("Infinite Loop detected in Engine Resolution Stack")

        current_step: GameStep = state.execution_stack.pop()

        result: StepResult = current_step.resolve(state, state.execution_context)

        # Collect events even from aborted steps
        collected_events.extend(result.events)

        # Handle Abort (GoA2 Rule: Mandatory step failure aborts action)
        if result.abort_action:
            print("   [ENGINE] Action aborted. Clearing remaining action steps.")
            _clear_to_finalize(state)
            continue

        if result.requires_input:
            # The step needs input. Put it back.
            state.execution_stack.append(current_step)
            _pending_events = collected_events
            # Convert InputRequest to dict for backwards compatibility
            if result.input_request is not None:
                return result.input_request.to_dict()
            return None

        if not result.is_finished:
            # Step wants to stay on stack (e.g. multi-turn or waiting)
            state.execution_stack.append(current_step)

        if result.new_steps:
            state.execution_stack.extend(reversed(result.new_steps))

    _pending_events = collected_events
    return None


def _clear_to_finalize(state: GameState):
    """
    Clears all steps from the stack until FinalizeHeroTurnStep is found.
    This effectively aborts the current action chain without skipping turn finalization.
    """
    from goa2.engine.steps import FinalizeHeroTurnStep

    while state.execution_stack:
        step = state.execution_stack[-1]
        if isinstance(step, FinalizeHeroTurnStep):
            break
        state.execution_stack.pop()
        print(f"   [ENGINE] Skipped step: {step.type}")


def push_steps(state: GameState, steps: list[GameStep]):
    """Helper to push new steps. Note: Stack is LIFO, so we extend in REVERSE order if we want them to execute 1, 2, 3."""
    # If we want Step 1 to run first, it must be at the TOP (end of list).
    # So if we have [S1, S2, S3], we should push S3, then S2, then S1.
    state.execution_stack.extend(reversed(steps))
