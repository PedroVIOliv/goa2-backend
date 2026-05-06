"""Base classes for the step engine: StepResult and GameStep."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from goa2.domain.events import GameEvent
from goa2.domain.input import InputRequest
from goa2.domain.models.enums import StepType
from goa2.domain.state import GameState


class StepResult(BaseModel):
    """Result of a step execution."""

    is_finished: bool = True
    requires_input: bool = False
    input_request: InputRequest | None = None
    new_steps: Sequence[GameStep] = Field(default_factory=list)
    abort_action: bool = False
    events: list[GameEvent] = Field(default_factory=list)


class GameStep(BaseModel):
    """
    Base class for all atomic game operations.
    Each step performs a single logic unit and can manage its own state.
    """

    type: StepType = StepType.GENERIC

    step_id: str = Field(default_factory=lambda: str(id(object())))
    pending_input: Any | None = None
    is_mandatory: bool = True
    active_if_key: str | None = None
    skip_if_key: str | None = None

    def should_skip(self, context: dict[str, Any]) -> bool:
        """Checks if the step should be skipped based on active_if_key or skip_if_key."""
        if self.active_if_key:
            val = context.get(self.active_if_key)
            if val is None:
                return True
        if self.skip_if_key:
            val = context.get(self.skip_if_key)
            if val is not None:
                return True
        return False

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        """
        Executes the step.
        :param state: Global GameState.
        :param context: Shared transient memory for the current Action chain.
        :return: StepResult indicating if we are done or need input.
        """
        raise NotImplementedError
