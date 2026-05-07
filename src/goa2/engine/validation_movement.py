from __future__ import annotations

from typing import TYPE_CHECKING, Any

from goa2.domain.models.effect import ActiveEffect, EffectType
from goa2.domain.models.enums import ActionType
from goa2.domain.types import BoardEntityID
from goa2.engine.validation_types import ValidationContext, ValidationResult

if TYPE_CHECKING:
    from goa2.domain.hex import Hex
    from goa2.domain.state import GameState


class MovementValidationMixin:
    if TYPE_CHECKING:
        # Provided at runtime by sibling Action/EffectValidationMixin in ValidationService.
        def can_perform_action(
            self,
            state: GameState,
            actor_id: str,
            action_type: ActionType,
            context: dict[str, Any] | ValidationContext | None = None,
        ) -> ValidationResult: ...
        def _is_effect_active(self, effect: ActiveEffect, state: GameState) -> bool: ...
        def _is_in_scope(
            self,
            effect: ActiveEffect,
            target_id: str,
            target_hex: Hex,
            state: GameState,
        ) -> bool: ...

    def can_move(
        self,
        state: GameState,
        unit_id: str,
        distance: int,
        context: dict[str, Any] | None = None,
        is_movement_action: bool = False,
    ) -> ValidationResult:
        """
        Can unit move 'distance' spaces?
        Checks: PREVENT_MOVEMENT status, movement restriction effects.
        """
        context = context or {}

        # Check action prevention (only applies to movement actions, not granted moves)
        if is_movement_action:
            action_result = self.can_perform_action(state, unit_id, ActionType.MOVEMENT, context)
            if not action_result.allowed:
                return action_result

        # Check movement cap effects
        unit_loc = state.entity_locations.get(BoardEntityID(unit_id))
        if not unit_loc:
            return ValidationResult.deny("Unit not on board")

        max_allowed = float("inf")
        blocking_effect = None

        for effect in state.active_effects:
            if effect.effect_type != EffectType.MOVEMENT_ZONE:
                continue
            if not self._is_effect_active(effect, state):
                continue
            if not self._is_in_scope(effect, unit_id, unit_loc, state):
                continue

            # Logic: If effect caps ONLY actions, and this is NOT an action -> Skip
            if effect.limit_actions_only and not is_movement_action:
                continue

            if effect.max_value is not None and effect.max_value < max_allowed:
                max_allowed = effect.max_value
                blocking_effect = effect

        if distance > max_allowed:
            return ValidationResult.deny(
                reason=f"Movement limited to {max_allowed} (attempted {distance})",
                effect_ids=[blocking_effect.id] if blocking_effect else [],
                source=blocking_effect.source_id if blocking_effect else None,
            )

        return ValidationResult.allow()
