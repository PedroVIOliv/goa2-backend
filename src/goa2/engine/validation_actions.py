from __future__ import annotations

from typing import TYPE_CHECKING, Any

from goa2.domain.models import Card
from goa2.domain.models.effect import EffectType
from goa2.domain.models.enums import ActionType, CardColor
from goa2.domain.types import BoardEntityID, UnitID
from goa2.engine.validation_types import ValidationContext, ValidationResult

if TYPE_CHECKING:
    from goa2.domain.state import GameState


class ActionValidationMixin:
    def can_perform_action(
        self,
        state: GameState,
        actor_id: str,
        action_type: ActionType,
        context: dict[str, Any] | ValidationContext | None = None,
    ) -> ValidationResult:
        """
        Can actor perform this action type?
        Checks: PREVENT_MOVEMENT, PREVENT_ATTACK, PREVENT_SKILL, etc.
        """
        context = context or {}

        # Helper to check exceptions
        def matches_exception(exceptions: list[CardColor]) -> bool:
            if not exceptions:
                return False
            # Check context for card
            card_obj = context.get("card")
            if card_obj and isinstance(card_obj, Card):
                return card_obj.current_color in exceptions
            return False

        # Check Active Effects (Zones/Auras) that restrict actions
        actor_loc = state.entity_locations.get(BoardEntityID(actor_id))
        if actor_loc:
            actor_unit = state.get_unit(UnitID(actor_id))

            for effect in state.active_effects:
                if not self._is_effect_active(effect, state):
                    continue

                # Check if this action is restricted by the effect
                if action_type not in effect.restrictions:
                    continue

                # Check for Color Exception
                if matches_exception(effect.except_card_colors):
                    continue

                # Check spatial/relational scope (is actor inside zone?)
                if not self._is_in_scope(effect, actor_id, actor_loc, state):
                    continue

                # Check if this actor is blocked by the effect
                if self._actor_blocked_by_effect(effect, actor_unit, None, state):
                    return ValidationResult.deny(
                        reason=f"Action prevented by effect: {effect.effect_type.value}",
                        effect_ids=[effect.id],
                        source=effect.source_id,
                    )

        return ValidationResult.allow()

    def can_fast_travel(
        self,
        state: GameState,
        unit_id: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Can unit perform Fast Travel?
        Checks: PREVENT_FAST_TRAVEL status.
        """
        return self.can_perform_action(state, unit_id, ActionType.FAST_TRAVEL, context)

    def can_repeat_action(
        self,
        state: GameState,
        actor_id: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Can actor repeat an action?
        Checks: PREVENT_ACTION_REPEAT effects.
        """
        # Check for repeat prevention via ActiveEffects
        actor_loc = state.entity_locations.get(BoardEntityID(actor_id))
        if actor_loc:
            actor_unit = state.get_unit(UnitID(actor_id))
            for effect in state.active_effects:
                if effect.effect_type != EffectType.REPEAT_PREVENTION:
                    continue
                if not self._is_effect_active(effect, state):
                    continue
                if not self._is_in_scope(effect, actor_id, actor_loc, state):
                    continue
                if self._actor_blocked_by_effect(effect, actor_unit, None, state):
                    return ValidationResult.deny(
                        reason="Action repeat prevented",
                        effect_ids=[effect.id],
                        source=effect.source_id,
                    )
        return ValidationResult.allow()
