"""Validation service and result types for effect system."""
from __future__ import annotations
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from pydantic import BaseModel, Field

from goa2.domain.models.enums import ActionType
from goa2.domain.models.modifier import Modifier, DurationType

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.hex import Hex


class ValidationResult(BaseModel):
    """
    Standardized result for all validation checks.
    Provides data for both execution logic and frontend previews.
    """
    allowed: bool
    reason: str = ""
    blocking_effect_ids: List[str] = Field(default_factory=list)
    blocking_modifier_ids: List[str] = Field(default_factory=list)
    blocked_by_source: Optional[str] = None

    @staticmethod
    def allow() -> "ValidationResult":
        """Create a result indicating the action is allowed."""
        return ValidationResult(allowed=True)

    @staticmethod
    def deny(
        reason: str,
        effect_ids: Optional[List[str]] = None,
        modifier_ids: Optional[List[str]] = None,
        source: Optional[str] = None
    ) -> "ValidationResult":
        """Create a result indicating the action is denied."""
        return ValidationResult(
            allowed=False,
            reason=reason,
            blocking_effect_ids=effect_ids or [],
            blocking_modifier_ids=modifier_ids or [],
            blocked_by_source=source
        )


class ValidationService:
    """
    Centralized validation authority.
    Single source of truth for "can X do Y to Z?"
    """

    # -------------------------------------------------------------------------
    # Primary Validation Methods (called by Steps and Filters)
    # -------------------------------------------------------------------------

    def can_perform_action(
        self,
        state: "GameState",
        actor_id: str,
        action_type: ActionType,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """
        Can actor perform this action type?
        Checks: PREVENT_MOVEMENT, PREVENT_ATTACK, PREVENT_SKILL, etc.
        """
        context = context or {}

        # Map action type to status tag
        prevention_tags = {
            ActionType.MOVEMENT: "PREVENT_MOVEMENT",
            ActionType.ATTACK: "PREVENT_ATTACK",
            ActionType.SKILL: "PREVENT_SKILL",
            ActionType.DEFENSE: "PREVENT_DEFENSE",
        }

        tag = prevention_tags.get(action_type)
        if not tag:
            return ValidationResult.allow()

        # Check modifiers on actor
        for mod in state.active_modifiers:
            if str(mod.target_id) == str(actor_id) and mod.status_tag == tag:
                if self._is_modifier_active(mod, state):
                    return ValidationResult.deny(
                        reason=f"Action prevented: {action_type.value}",
                        modifier_ids=[mod.id],
                        source=mod.source_id
                    )

        return ValidationResult.allow()

    def can_be_placed(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        destination: Optional["Hex"] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """
        Can unit_id be placed/teleported by actor_id?
        Handles: Magnetic Dagger, Bulwark, displacement prevention.

        Args:
            unit_id: The unit being moved/placed
            actor_id: The hero performing the action
            destination: Target hex (optional, for destination-specific checks)
        """
        context = context or {}

        unit = state.get_unit(unit_id)
        actor = state.get_unit(actor_id)

        if not unit:
            return ValidationResult.deny("Unit not found")

        # Destination validation (if provided)
        if destination:
            tile = state.board.get_tile(destination)
            if not tile:
                return ValidationResult.deny("Destination not on board")
            if tile.is_occupied:
                return ValidationResult.deny("Destination occupied")

        # Check status-based prevention on the unit
        for mod in state.active_modifiers:
            if str(mod.target_id) == str(unit_id) and mod.status_tag == "PREVENT_PLACEMENT":
                if self._is_modifier_active(mod, state):
                    # Check if actor is blocked by this modifier
                    if self._actor_blocked_by_modifier(mod, actor, unit, state):
                        return ValidationResult.deny(
                            reason="Unit cannot be placed",
                            modifier_ids=[mod.id],
                            source=mod.source_id
                        )

        # Check spatial placement prevention effects (ActiveEffects)
        # For Phase 1, we implement the basic pattern
        # Full spatial effect checking comes in later phases

        return ValidationResult.allow()

    def can_be_pushed(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Can unit_id be pushed by actor_id?"""
        return self.can_be_placed(state, unit_id, actor_id, None, context)

    def can_be_swapped(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Can unit_id be swapped by actor_id?"""
        return self.can_be_placed(state, unit_id, actor_id, None, context)

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _is_modifier_active(self, mod: Modifier, state: "GameState") -> bool:
        """
        Check if modifier is currently active.
        Order matters: (1) Check PASSIVE first, (2) Card state, (3) Duration timing.
        """
        # PASSIVE effects are ALWAYS active
        if mod.duration == DurationType.PASSIVE:
            return True

        # Card-based effects require source card to be in played state
        if mod.source_card_id:
            if not self._is_card_in_played_state(state, mod.source_id, mod.source_card_id):
                return False

        # Check temporal duration
        if mod.duration == DurationType.THIS_TURN:
            return state.turn == mod.created_at_turn and state.round == mod.created_at_round

        if mod.duration == DurationType.NEXT_TURN:
            # Active on the turn AFTER creation (within same round only!)
            if state.round == mod.created_at_round:
                return state.turn == mod.created_at_turn + 1
            return False  # Cross-round NEXT_TURN never activates

        if mod.duration == DurationType.THIS_ROUND:
            return state.round == mod.created_at_round

        return False

    def _is_card_in_played_state(
        self,
        state: "GameState",
        hero_id: str,
        card_id: str
    ) -> bool:
        """
        Check if a card is currently in the hero's played state.
        A card is "played" if it's in hero.played_cards OR hero.current_turn_card.
        """
        hero = state.get_hero(hero_id)
        if not hero:
            return False

        # Check current turn card (UNRESOLVED)
        if hero.current_turn_card and hero.current_turn_card.id == card_id:
            return True

        # Check played cards (RESOLVED)
        for card in hero.played_cards:
            if card.id == card_id:
                return True

        return False

    def _actor_blocked_by_modifier(
        self,
        mod: Modifier,
        actor: Any,
        target: Any,
        state: "GameState"
    ) -> bool:
        """Determine if actor is blocked by this modifier."""
        # For now, modifiers on a target block all enemy actions
        if not actor or not target:
            return False

        actor_team = getattr(actor, 'team', None)
        target_team = getattr(target, 'team', None)

        if actor_team is None or target_team is None:
            return False

        # Enemy trying to displace protected unit
        return actor_team != target_team
