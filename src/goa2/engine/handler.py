from __future__ import annotations

import logging
from dataclasses import dataclass, field

import goa2.engine.step_types as _step_types  # noqa: F401 — patches model annotations
from goa2.domain.events import GameEvent
from goa2.domain.input import InputRequest, InputResponse
from goa2.domain.models import GamePhase
from goa2.domain.models.effect import EffectType
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
            request = result.input_request
            controller_id = _action_controller(state, request.player_id) if request else None
            if request is not None and controller_id is not None:
                request.context["controlled_hero_id"] = request.player_id
                request.player_id = controller_id
            # Track rollback disabled: if input targets someone other than the
            # current actor. A control remap does NOT disable rollback — the
            # controller confirms/rolls back the controlled action.
            if (
                request is not None
                and controller_id is None
                and state.current_actor_id is not None
                and request.player_id != str(state.current_actor_id)
            ):
                state.execution_context["rollback_disabled"] = True
            return StackResult(input_request=request, events=collected_events)

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


def _action_controller(state: GameState, player_id: str) -> str | None:
    """The Ultimate Trick (Hanu): if `player_id` is the current actor and an
    active CONTROL_NEXT_ACTION effect targets them for the exact card they are
    resolving, return the controlling hero's id. The remap changes only who
    answers — options/legality were already computed relative to the actor."""
    if state.current_actor_id is None or player_id != str(state.current_actor_id):
        return None
    hero = state.get_hero(state.current_actor_id)
    if hero is None or hero.current_turn_card is None:
        return None
    for effect in state.active_effects:
        if (
            effect.effect_type == EffectType.CONTROL_NEXT_ACTION
            and effect.is_active
            and effect.scope.origin_id == player_id
            and effect.controlled_card_id == hero.current_turn_card.id
        ):
            return effect.source_id
    return None


def push_steps(state: GameState, steps: list[GameStep]):
    """Helper to push new steps. Note: Stack is LIFO, so we extend in REVERSE order if we want them to execute 1, 2, 3."""
    # If we want Step 1 to run first, it must be at the TOP (end of list).
    # So if we have [S1, S2, S3], we should push S3, then S2, then S1.
    state.execution_stack.extend(reversed(steps))
