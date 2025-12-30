from typing import Dict, Any, Optional
from goa2.domain.state import GameState
from goa2.engine.steps import GameStep, StepResult

def process_resolution_stack(state: GameState) -> Optional[Dict[str, Any]]:
    """
    Main Engine Loop for the Step-Based System.
    """
    safety_counter = 0
    MAX_STEPS = 1000

    while state.execution_stack:
        safety_counter += 1
        if safety_counter > MAX_STEPS:
            raise RuntimeError("Infinite Loop detected in Engine Resolution Stack")

        # 1. Pop the top step
        current_step: GameStep = state.execution_stack.pop()
        
        # 2. Resolve
        result: StepResult = current_step.resolve(state, state.execution_context)
        
        # 3. Handle Abort (GoA2 Rule: Mandatory step failure aborts action)
        if result.abort_action:
            print("   [ENGINE] Action aborted. Clearing remaining action steps.")
            _clear_to_finalize(state)
            continue
        
        # 4. Handle Result
        
        if result.requires_input:
            # The step needs input. Put it back.
            state.execution_stack.append(current_step)
            return result.input_request

        if not result.is_finished:
            # Step wants to stay on stack (e.g. multi-turn or waiting)
            state.execution_stack.append(current_step)
            
        # 5. Handle Spawned Steps
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
    # state.execution_stack.extend(reversed(steps))
    
    # Wait, simple list.pop() removes the last element.
    # So the "Top" is the last element.
    # If I want to run S1, then S2.
    # Stack: [S2, S1] -> pop S1 -> run S1 -> pop S2 -> run S2.
    # So yes, we reverse them.
    state.execution_stack.extend(reversed(steps))
