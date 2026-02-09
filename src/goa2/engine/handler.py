from typing import Dict, Any, Optional, Union
from goa2.domain.state import GameState
from goa2.domain.models import GamePhase
from goa2.domain.input import InputRequest, InputResponse
from goa2.engine.steps import GameStep, StepResult


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


def process_stack(state: GameState) -> Optional[InputRequest]:
    """Process the execution stack, returning typed InputRequest or None."""
    safety_counter = 0
    MAX_STEPS = 1000

    if state.phase == GamePhase.GAME_OVER:
        return None

    while state.execution_stack:
        safety_counter += 1
        if safety_counter > MAX_STEPS:
            raise RuntimeError("Infinite Loop detected in Engine Resolution Stack")

        current_step: GameStep = state.execution_stack.pop()
        result: StepResult = current_step.resolve(state, state.execution_context)

        if result.abort_action:
            _clear_to_finalize(state)
            continue

        if result.requires_input:
            state.execution_stack.append(current_step)
            return result.input_request

        if not result.is_finished:
            state.execution_stack.append(current_step)

        if result.new_steps:
            state.execution_stack.extend(reversed(result.new_steps))

    return None


def process_resolution_stack(state: GameState) -> Optional[Dict[str, Any]]:
    """
    Main Engine Loop for the Step-Based System.

    Returns a dict representation of InputRequest for backwards compatibility.
    The internal steps now use typed InputRequest models.
    """
    safety_counter = 0
    MAX_STEPS = 1000

    if state.phase == GamePhase.GAME_OVER:
        print("   [ENGINE] Game is Over. Halting execution.")
        return None

    while state.execution_stack:
        safety_counter += 1
        if safety_counter > MAX_STEPS:
            raise RuntimeError("Infinite Loop detected in Engine Resolution Stack")

        current_step: GameStep = state.execution_stack.pop()

        result: StepResult = current_step.resolve(state, state.execution_context)

        # Handle Abort (GoA2 Rule: Mandatory step failure aborts action)
        if result.abort_action:
            print("   [ENGINE] Action aborted. Clearing remaining action steps.")
            _clear_to_finalize(state)
            continue

        if result.requires_input:
            # The step needs input. Put it back.
            state.execution_stack.append(current_step)
            # Convert InputRequest to dict for backwards compatibility
            if result.input_request is not None:
                return result.input_request.to_dict()
            return None

        if not result.is_finished:
            # Step wants to stay on stack (e.g. multi-turn or waiting)
            state.execution_stack.append(current_step)

        if result.new_steps:
            state.execution_stack.extend(reversed(result.new_steps))

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
