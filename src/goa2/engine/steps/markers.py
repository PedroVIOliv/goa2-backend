"""Token and marker placement/removal steps."""

from __future__ import annotations

import logging
from typing import Any

from goa2.domain.events import GameEvent, GameEventType, _hex_dict
from goa2.domain.hex import Hex
from goa2.domain.models import StepType, TargetType, Token, TokenType
from goa2.domain.models.marker import MarkerType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID
from goa2.engine import rules
from goa2.engine.filters_units import TokenTypeFilter, UnitTypeFilter
from goa2.engine.steps.base import GameStep, StepResult

logger = logging.getLogger(__name__)


def _remove_token_from_board(state: GameState, token_id: str) -> tuple[Hex | None, int]:
    from_hex = state.entity_locations.get(BoardEntityID(token_id))
    if not from_hex:
        return None, 0

    state.remove_entity(BoardEntityID(token_id))

    initial_count = len(state.active_effects)
    state.active_effects = [
        e for e in state.active_effects if e.source_id != token_id and e.scope.origin_id != token_id
    ]
    removed_effects = initial_count - len(state.active_effects)

    if removed_effects > 0:
        logger.debug(f"   [TOKEN] Removed {removed_effects} linked effect(s) from token {token_id}")

    return from_hex, removed_effects


class RemoveTokenStep(GameStep):
    type: StepType = StepType.REMOVE_TOKEN
    token_id: str | None = None
    token_key: str | None = None

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        target_id = self.token_id
        if self.token_key:
            target_id = context.get(self.token_key)
        if not target_id:
            return StepResult(is_finished=True)

        token = state.misc_entities.get(BoardEntityID(target_id))
        if not isinstance(token, Token):
            return StepResult(is_finished=True)

        from_hex, removed_effects = _remove_token_from_board(state, target_id)
        if not from_hex:
            return StepResult(is_finished=True)

        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.TOKEN_REMOVED,
                    actor_id=str(state.current_actor_id) if state.current_actor_id else None,
                    target_id=target_id,
                    from_hex=_hex_dict(from_hex),
                    metadata={"effects_removed": removed_effects},
                )
            ],
        )


class PlaceTokenStep(GameStep):
    type: StepType = StepType.PLACE_TOKEN
    token_type: TokenType
    hex_key: str = "target_hex"
    owner_id_key: str | None = None
    output_key: str | None = None
    overflow_selection_key: str = "overflow_token_to_remove"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.selection import SelectStep

        dest_val = context.get(self.hex_key)
        if not dest_val:
            return StepResult(is_finished=True)

        dest_hex = Hex(**dest_val) if isinstance(dest_val, dict) else dest_val
        tile = state.board.get_tile(dest_hex)
        if tile and tile.is_occupied:
            logger.debug(
                f"   [TOKEN] Cannot place {self.token_type.value} at {dest_hex}: occupied."
            )
            return StepResult(is_finished=True)

        owner_id = context.get(self.owner_id_key) if self.owner_id_key else None
        if owner_id is None:
            owner_id = state.current_actor_id

        pool = state.token_pool.get(self.token_type, [])
        available = next(
            (t for t in pool if BoardEntityID(str(t.id)) not in state.entity_locations),
            None,
        )

        events: list[GameEvent] = []

        if available is None:
            placed = [t for t in pool if BoardEntityID(str(t.id)) in state.entity_locations]
            if not placed:
                return StepResult(is_finished=True)
            return StepResult(
                is_finished=True,
                new_steps=[
                    SelectStep(
                        target_type=TargetType.UNIT_OR_TOKEN,
                        prompt=f"Select a {self.token_type.value} token to remove from the board.",
                        output_key=self.overflow_selection_key,
                        skip_immunity_filter=True,
                        skip_self_filter=True,
                        is_mandatory=True,
                        filters=[
                            UnitTypeFilter(unit_type="TOKEN"),
                            TokenTypeFilter(token_type=self.token_type),
                        ],
                        override_player_id_key=self.owner_id_key,
                    ),
                    RemoveTokenStep(token_key=self.overflow_selection_key),
                    PlaceTokenStep(
                        token_type=self.token_type,
                        hex_key=self.hex_key,
                        owner_id_key=self.owner_id_key,
                        output_key=self.output_key,
                        overflow_selection_key=self.overflow_selection_key,
                    ),
                ],
            )

        if owner_id is not None:
            available.owner_id = HeroID(str(owner_id))

        state.place_entity(BoardEntityID(str(available.id)), dest_hex)
        if self.output_key:
            context[self.output_key] = str(available.id)

        events.append(
            GameEvent(
                event_type=GameEventType.TOKEN_PLACED,
                actor_id=str(owner_id) if owner_id else None,
                target_id=str(available.id),
                to_hex=_hex_dict(dest_hex),
                metadata={"token_type": self.token_type.value},
            )
        )
        return StepResult(is_finished=True, events=events)


class MoveTokenStep(GameStep):
    type: StepType = StepType.MOVE_TOKEN
    token_key: str
    destination_key: str = "target_hex"
    range_val: int = 1
    pass_through_obstacles: bool = False

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        token_id = context.get(self.token_key)
        dest_val = context.get(self.destination_key)
        if not token_id or not dest_val:
            return StepResult(is_finished=True)

        token = state.misc_entities.get(BoardEntityID(str(token_id)))
        if not isinstance(token, Token):
            return StepResult(is_finished=True)

        dest_hex = Hex(**dest_val) if isinstance(dest_val, dict) else dest_val
        from_hex = state.entity_locations.get(BoardEntityID(str(token_id)))
        if not from_hex:
            return StepResult(is_finished=True)

        tile = state.board.get_tile(dest_hex)
        if tile and tile.is_occupied and str(tile.occupant_id) != str(token_id):
            logger.debug(f"   [TOKEN] Cannot move {token_id} to {dest_hex}: occupied.")
            return StepResult(is_finished=True)

        if from_hex != dest_hex:
            is_valid = rules.validate_movement_path(
                board=state.board,
                start=from_hex,
                end=dest_hex,
                max_steps=self.range_val,
                state=state,
                actor_id=str(state.current_actor_id) if state.current_actor_id else None,
                pass_through_obstacles=self.pass_through_obstacles,
            )
            if not is_valid:
                logger.debug(f"   [TOKEN] Invalid token move {token_id}: blocked or out of range.")
                return StepResult(is_finished=True)
        else:
            return StepResult(is_finished=True)

        state.place_entity(BoardEntityID(str(token_id)), dest_hex)
        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.TOKEN_MOVED,
                    actor_id=str(state.current_actor_id) if state.current_actor_id else None,
                    target_id=str(token_id),
                    from_hex=_hex_dict(from_hex),
                    to_hex=_hex_dict(dest_hex),
                    metadata={"range": self.range_val},
                )
            ],
        )


class PlaceMarkerStep(GameStep):
    """
    Places a marker on a target hero.

    Markers are singletons - placing on a new target automatically removes
    from the previous target. The marker's effects are applied via
    get_computed_stat() which reads markers directly.

    Usage:
        PlaceMarkerStep(
            marker_type=MarkerType.VENOM,
            target_key="victim_id",
            value=-1,
        )
    """

    type: StepType = StepType.PLACE_MARKER
    marker_type: MarkerType
    target_id: str | None = None  # Direct target ID
    target_key: str | None = None  # Context key for target ID
    value: int = 0  # Effect magnitude (e.g., -1 or -2 for Venom)

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.effects import CheckPassiveAbilitiesStep

        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve target
        target = self.target_id
        if not target and self.target_key:
            target = context.get(self.target_key)

        if not target:
            logger.debug(f"   [SKIP] No target for PlaceMarkerStep ({self.marker_type.value})")
            return StepResult(is_finished=True)

        # Get source (current actor)
        source_id = str(state.current_actor_id) if state.current_actor_id else "system"

        # Place the marker
        state.place_marker(
            marker_type=self.marker_type,
            target_id=target,
            value=self.value,
            source_id=source_id,
        )

        logger.debug(
            f"   [MARKER] Placed {self.marker_type.value} on {target} "
            f"(value={self.value}, source={source_id})"
        )

        # Fire AFTER_PLACE_MARKER passive trigger
        from goa2.domain.models.enums import PassiveTrigger

        context["marker_target_id"] = target
        post_steps: list[GameStep] = [
            CheckPassiveAbilitiesStep(trigger=PassiveTrigger.AFTER_PLACE_MARKER.value)
        ]

        return StepResult(
            is_finished=True,
            new_steps=post_steps,
            events=[
                GameEvent(
                    event_type=GameEventType.MARKER_PLACED,
                    actor_id=source_id,
                    target_id=target,
                    metadata={
                        "marker_type": self.marker_type.value,
                        "value": self.value,
                    },
                )
            ],
        )


class RemoveMarkerStep(GameStep):
    """
    Removes a marker, returning it to supply.

    Usage:
        RemoveMarkerStep(marker_type=MarkerType.VENOM)
    """

    type: StepType = StepType.REMOVE_MARKER
    marker_type: MarkerType

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        marker = state.remove_marker(self.marker_type)

        if marker:
            logger.debug(f"   [MARKER] Removed {self.marker_type.value} from play")
            return StepResult(
                is_finished=True,
                events=[
                    GameEvent(
                        event_type=GameEventType.MARKER_REMOVED,
                        metadata={"marker_type": self.marker_type.value},
                    )
                ],
            )
        else:
            logger.debug(f"   [MARKER] {self.marker_type.value} not in play")

        return StepResult(is_finished=True)
