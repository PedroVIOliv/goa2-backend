from __future__ import annotations

from typing import TYPE_CHECKING, Any

from goa2.domain.models.effect import ActiveEffect, EffectType
from goa2.domain.types import BoardEntityID
from goa2.engine.validation_types import ValidationResult

if TYPE_CHECKING:
    from goa2.domain.hex import Hex
    from goa2.domain.state import GameState


class TargetingValidationMixin:
    if TYPE_CHECKING:
        # Provided at runtime by sibling EffectValidationMixin in ValidationService.
        def _is_effect_active(self, effect: ActiveEffect, state: GameState) -> bool: ...
        def _get_origin_hex(self, effect: ActiveEffect, state: GameState) -> Hex | None: ...
        def _actor_blocked_by_effect(
            self, effect: ActiveEffect, actor: Any, target: Any, state: GameState
        ) -> bool: ...

    def can_be_targeted(
        self,
        state: GameState,
        actor_id: str,
        target_id: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Can actor target target_id?
        Checks: Line of Sight (Smoke Bomb), Invisibility (Future), etc.
        """
        if not actor_id or not target_id:
            return ValidationResult.deny("Invalid actor or target")

        actor_loc = state.entity_locations.get(BoardEntityID(actor_id))
        target_loc = state.entity_locations.get(BoardEntityID(target_id))

        if not actor_loc or not target_loc:
            # If not on board, targeting is usually impossible unless global effect
            return ValidationResult.deny("Actor or target not on board")

        # Check LOS Blockers (Smoke Bomb)
        # Iterate all active effects of type LOS_BLOCKER
        for effect in state.active_effects:
            if effect.effect_type != EffectType.LOS_BLOCKER:
                continue
            if not self._is_effect_active(effect, state):
                continue

            # Check if this effect acts as a blocker
            # Origin of the effect (e.g. the Smoke Bomb token hex)
            blocker_hex = self._get_origin_hex(effect, state)
            if not blocker_hex:
                continue

            if blocker_hex.is_on_segment(actor_loc, target_loc, exclusive=True):
                actor_entity = state.get_entity(BoardEntityID(actor_id))
                target_entity = state.get_entity(BoardEntityID(target_id))
                if not self._actor_blocked_by_effect(effect, actor_entity, target_entity, state):
                    continue
                return ValidationResult.deny(
                    reason="Line of sight blocked",
                    effect_ids=[effect.id],
                    source=effect.source_id,
                )

        return ValidationResult.allow()
