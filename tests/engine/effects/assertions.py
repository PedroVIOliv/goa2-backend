from __future__ import annotations

from typing import Any

from goa2.domain.events import GameEvent, GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequest
from goa2.domain.models.effect import EffectType
from goa2.domain.state import GameState

from .builders import Coords, hex_at


def assert_position(state: GameState, entity_id: str, coords: Coords) -> None:
    expected = hex_at(coords)
    actual = state.entity_locations.get(entity_id)
    assert actual == expected, f"Expected {entity_id} at {expected}, got {actual}"


def assert_effect_active(
    state: GameState,
    effect_type: EffectType,
    *,
    source_id: str | None = None,
) -> None:
    matches = [
        effect
        for effect in state.active_effects
        if effect.effect_type == effect_type
        and effect.is_active
        and (source_id is None or effect.source_id == source_id)
    ]
    assert (
        matches
    ), f"Expected active {effect_type} effect from {source_id}, got {state.active_effects}"


def assert_valid_options(
    req: InputRequest | None,
    *,
    contains: list[Any] | None = None,
    excludes: list[Any] | None = None,
) -> None:
    assert req is not None, "Expected an input request with valid options, got None"
    data = req.to_dict()
    options = data.get("valid_options", data.get("valid_hexes", data.get("options", [])))
    normalized_options = {_normalize_option(option) for option in options}

    for expected in contains or []:
        assert (
            _normalize_option(expected) in normalized_options
        ), f"Expected option {expected!r} in {options!r}"

    for excluded in excludes or []:
        assert (
            _normalize_option(excluded) not in normalized_options
        ), f"Expected option {excluded!r} to be excluded from {options!r}"


def assert_event_emitted(
    events: list[GameEvent],
    event_type: GameEventType,
    **fields: Any,
) -> None:
    for event in events:
        if event.event_type != event_type:
            continue
        if all(getattr(event, key) == value for key, value in fields.items()):
            return
    raise AssertionError(f"Expected event {event_type} with {fields}, got {events}")


def _normalize_option(option: Any) -> Any:
    if isinstance(option, Hex):
        return (option.q, option.r, option.s)
    if isinstance(option, tuple):
        return option
    if isinstance(option, dict):
        if {"q", "r", "s"}.issubset(option):
            return (option["q"], option["r"], option["s"])
        if "id" in option:
            return option["id"]
    return option
