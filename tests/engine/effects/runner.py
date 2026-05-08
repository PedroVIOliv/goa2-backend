from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from goa2.domain.events import GameEvent
from goa2.domain.input import InputRequest, InputRequestType
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import FinalizeHeroTurnStep, ResolveCardStep


def run_card(state: GameState, hero_id: str, *, finalize_turn: bool = False) -> EffectRun:
    steps = [ResolveCardStep(hero_id=hero_id)]
    if finalize_turn:
        steps.append(FinalizeHeroTurnStep(hero_id=hero_id))
    push_steps(state, steps)
    return EffectRun(state=state, hero_id=hero_id)


@dataclass
class EffectRun:
    state: GameState
    hero_id: str
    latest_request: InputRequest | None = None
    events: list[GameEvent] = field(default_factory=list)

    def expect_input(self, input_type: str | InputRequestType) -> Self:
        result = process_stack(self.state)
        self.events.extend(result.events)
        self.latest_request = result.input_request
        expected = input_type.value if isinstance(input_type, InputRequestType) else input_type
        actual = self.latest_request.request_type.value if self.latest_request else None
        assert actual == expected, self._failure_dump(
            f"Expected input {expected!r}, got {actual!r}"
        )
        return self

    def choose(self, value: Any) -> Self:
        assert self.latest_request is not None, self._failure_dump("No pending input to answer")
        assert self.state.execution_stack, self._failure_dump("No stack step waiting for input")
        self.state.execution_stack[-1].pending_input = {"selection": value}
        self.latest_request = None
        return self

    def skip(self) -> Self:
        return self.choose("SKIP")

    def confirm(self) -> Self:
        return self.choose("YES")

    def finish(self) -> Self:
        result = process_stack(self.state)
        self.events.extend(result.events)
        self.latest_request = result.input_request
        assert self.latest_request is None, self._failure_dump("Expected stack to finish")
        return self

    def _failure_dump(self, message: str) -> str:
        stack_types = [
            getattr(step, "type", type(step).__name__) for step in self.state.execution_stack
        ]
        context = dict(self.state.execution_context)
        request = self.latest_request.to_dict() if self.latest_request else None
        event_types = [event.event_type.value for event in self.events]
        return (
            f"{message}\n"
            f"hero_id={self.hero_id!r}\n"
            f"stack={stack_types!r}\n"
            f"context={context!r}\n"
            f"latest_request={request!r}\n"
            f"events={event_types!r}"
        )
