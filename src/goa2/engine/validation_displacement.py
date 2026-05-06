from __future__ import annotations

from typing import TYPE_CHECKING, Any

from goa2.domain.models.effect import EffectType
from goa2.domain.models.enums import DisplacementType
from goa2.domain.types import BoardEntityID
from goa2.engine.validation_types import ValidationResult

if TYPE_CHECKING:
    from goa2.domain.hex import Hex
    from goa2.domain.state import GameState


class DisplacementValidationMixin:
    def can_be_placed(
        self,
        state: GameState,
        unit_id: str,
        actor_id: str,
        destination: Hex | None = None,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Can unit_id be placed/teleported by actor_id?
        Handles: Magnetic Dagger, Bulwark, displacement prevention.

        Supports both Units (Heroes, Minions) and Tokens.

        Args:
            unit_id: The entity being moved/placed (unit or token)
            actor_id: The hero performing the action
            destination: Target hex (optional, for destination-specific checks)
        """
        context = context or {}

        entity = state.get_entity(BoardEntityID(unit_id))
        actor = state.get_entity(BoardEntityID(actor_id))

        if not entity:
            return ValidationResult.deny("Entity not found")

        if destination:
            tile = state.board.get_tile(destination)
            if not tile:
                return ValidationResult.deny("Destination not on board")
            if tile.is_occupied:
                return ValidationResult.deny("Destination occupied")

        entity_loc = state.entity_locations.get(BoardEntityID(unit_id))
        if not entity_loc:
            return ValidationResult.allow()

        return self._check_displacement_prevention(
            state=state,
            unit_id=unit_id,
            actor_id=actor_id,
            entity=entity,
            actor=actor,
            entity_loc=entity_loc,
            displacement_type=DisplacementType.PLACE,
        )

    def can_be_moved(
        self,
        state: GameState,
        unit_id: str,
        actor_id: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Can unit_id be moved (walked/stepped) by actor_id?
        Handles: Noble Blade nudge, Bulwark move prevention.
        """
        context = context or {}

        entity = state.get_entity(BoardEntityID(unit_id))
        actor = state.get_entity(BoardEntityID(actor_id))

        if not entity:
            return ValidationResult.deny("Entity not found")

        entity_loc = state.entity_locations.get(BoardEntityID(unit_id))
        if not entity_loc:
            return ValidationResult.allow()

        return self._check_displacement_prevention(
            state=state,
            unit_id=unit_id,
            actor_id=actor_id,
            entity=entity,
            actor=actor,
            entity_loc=entity_loc,
            displacement_type=DisplacementType.MOVE,
        )

    def can_be_pushed(
        self,
        state: GameState,
        unit_id: str,
        actor_id: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Can unit_id be pushed by actor_id?
        Handles: Kinetic Repulse, Bulwark push prevention.
        """
        context = context or {}

        entity = state.get_entity(BoardEntityID(unit_id))
        actor = state.get_entity(BoardEntityID(actor_id))

        if not entity:
            return ValidationResult.deny("Entity not found")

        entity_loc = state.entity_locations.get(BoardEntityID(unit_id))
        if not entity_loc:
            return ValidationResult.allow()

        return self._check_displacement_prevention(
            state=state,
            unit_id=unit_id,
            actor_id=actor_id,
            entity=entity,
            actor=actor,
            entity_loc=entity_loc,
            displacement_type=DisplacementType.PUSH,
        )

    def can_be_swapped(
        self,
        state: GameState,
        unit_id: str,
        actor_id: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Can unit_id be swapped by actor_id?
        Handles: Arcane Whirlpool, Ebb and Flow, Bulwark swap prevention.
        """
        context = context or {}

        entity = state.get_entity(BoardEntityID(unit_id))
        actor = state.get_entity(BoardEntityID(actor_id))

        if not entity:
            return ValidationResult.deny("Entity not found")

        entity_loc = state.entity_locations.get(BoardEntityID(unit_id))
        if not entity_loc:
            return ValidationResult.allow()

        return self._check_displacement_prevention(
            state=state,
            unit_id=unit_id,
            actor_id=actor_id,
            entity=entity,
            actor=actor,
            entity_loc=entity_loc,
            displacement_type=DisplacementType.SWAP,
        )

    def _check_displacement_prevention(
        self,
        state: GameState,
        unit_id: str,
        actor_id: str,
        entity: Any,
        actor: Any,
        entity_loc: Hex,
        displacement_type: DisplacementType,
    ) -> ValidationResult:
        """
        Internal helper to check displacement prevention effects.
        Checks if the effect blocks this specific type of displacement.
        """
        for effect in state.active_effects:
            if effect.effect_type != EffectType.PLACEMENT_PREVENTION:
                continue
            if not self._is_effect_active(effect, state):
                continue
            if not self._is_in_scope(effect, unit_id, entity_loc, state):
                continue

            if displacement_type not in effect.displacement_blocks:
                continue

            if self._actor_blocked_by_effect(effect, actor, entity, state):
                return ValidationResult.deny(
                    reason=f"{displacement_type.value} prevented by area effect",
                    effect_ids=[effect.id],
                    source=effect.source_id,
                )

        return ValidationResult.allow()
