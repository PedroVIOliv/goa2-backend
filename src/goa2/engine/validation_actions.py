from __future__ import annotations

from typing import TYPE_CHECKING, Any

from goa2.domain.models import Card
from goa2.domain.models.effect import ActiveEffect, EffectType
from goa2.domain.models.enums import ActionType, CardColor
from goa2.domain.types import HeroID, UnitID
from goa2.engine.validation_types import ValidationContext, ValidationResult

if TYPE_CHECKING:
    from goa2.domain.hex import Hex
    from goa2.domain.state import GameState


class ActionValidationMixin:
    if TYPE_CHECKING:
        # Provided at runtime by sibling EffectValidationMixin in ValidationService.
        def _is_effect_active(self, effect: ActiveEffect, state: GameState) -> bool: ...
        def _is_in_scope(
            self,
            effect: ActiveEffect,
            target_id: str,
            target_hex: Hex,
            state: GameState,
        ) -> bool: ...
        def _actor_blocked_by_effect(
            self, effect: ActiveEffect, actor: Any, target: Any, state: GameState
        ) -> bool: ...

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

        # First restriction effect (if any) that blocks the entity standing at
        # check_hex. Scope + block checks use check_id so a multi-piece hero can
        # be evaluated per-piece (team + self identity resolve through the piece).
        def blocking_effect(check_id: str, check_hex: Hex) -> ActiveEffect | None:
            actor_unit = state.get_unit(UnitID(check_id))
            for effect in state.active_effects:
                if not self._is_effect_active(effect, state):
                    continue
                if action_type not in effect.restrictions:
                    continue
                if matches_exception(effect.except_card_colors):
                    continue
                if not self._is_in_scope(effect, check_id, check_hex, state):
                    continue
                if self._actor_blocked_by_effect(effect, actor_unit, None, state):
                    return effect
            return None

        # Check Active Effects (Zones/Auras) that restrict actions.
        actor_loc = state.get_position(actor_id)
        if actor_loc:
            blocked = blocking_effect(actor_id, actor_loc)
            if blocked:
                return ValidationResult.deny(
                    reason=f"Action prevented by effect: {blocked.effect_type.value}",
                    effect_ids=[blocked.id],
                    source=blocked.source_id,
                )
            return ValidationResult.allow()

        # Unbound multi-piece hero: each piece is an independent actor. The hero
        # can perform the action if ANY piece can; deny only if every on-board
        # piece is blocked (the acting piece is chosen later, per-piece).
        hero = state.get_hero(HeroID(actor_id))
        if hero is not None and hero.is_multi_piece:
            last_blocked: ActiveEffect | None = None
            has_piece = False
            for pid in state.get_piece_ids(actor_id):
                piece_loc = state.get_position(pid)
                if piece_loc is None:
                    continue
                has_piece = True
                blocked = blocking_effect(pid, piece_loc)
                if blocked is None:
                    return ValidationResult.allow()
                last_blocked = blocked
            if has_piece and last_blocked is not None:
                return ValidationResult.deny(
                    reason=f"Action prevented by effect: {last_blocked.effect_type.value}",
                    effect_ids=[last_blocked.id],
                    source=last_blocked.source_id,
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

        # First repeat-prevention effect (if any) blocking the entity at
        # check_hex. Uses check_id so a multi-piece hero can be evaluated
        # per-piece (team + self identity resolve through the piece).
        def blocking_effect(check_id: str, check_hex: Hex) -> ActiveEffect | None:
            actor_unit = state.get_unit(UnitID(check_id))
            for effect in state.active_effects:
                if effect.effect_type != EffectType.REPEAT_PREVENTION:
                    continue
                if not self._is_effect_active(effect, state):
                    continue
                if not self._is_in_scope(effect, check_id, check_hex, state):
                    continue
                if self._actor_blocked_by_effect(effect, actor_unit, None, state):
                    return effect
            return None

        # Check for repeat prevention via ActiveEffects.
        actor_loc = state.get_position(actor_id)
        if actor_loc:
            blocked = blocking_effect(actor_id, actor_loc)
            if blocked:
                return ValidationResult.deny(
                    reason="Action repeat prevented",
                    effect_ids=[blocked.id],
                    source=blocked.source_id,
                )
            return ValidationResult.allow()

        # Unbound multi-piece hero: each piece is an independent actor. The hero
        # can repeat if ANY piece can; deny only if every on-board piece is
        # blocked (the acting piece is chosen later, per-piece).
        hero = state.get_hero(HeroID(actor_id))
        if hero is not None and hero.is_multi_piece:
            last_blocked: ActiveEffect | None = None
            has_piece = False
            for pid in state.get_piece_ids(actor_id):
                piece_loc = state.get_position(pid)
                if piece_loc is None:
                    continue
                has_piece = True
                blocked = blocking_effect(pid, piece_loc)
                if blocked is None:
                    return ValidationResult.allow()
                last_blocked = blocked
            if has_piece and last_blocked is not None:
                return ValidationResult.deny(
                    reason="Action repeat prevented",
                    effect_ids=[last_blocked.id],
                    source=last_blocked.source_id,
                )

        return ValidationResult.allow()
