"""Validation service and result types for effect system."""

from __future__ import annotations
from typing import List, Optional, Dict, Any, TYPE_CHECKING, cast, Union

from pydantic import BaseModel, Field

from goa2.domain.types import BoardEntityID, UnitID, HeroID
from goa2.domain.models.enums import ActionType
from goa2.domain.models.modifier import Modifier, DurationType
from goa2.domain.models.effect import ActiveEffect, EffectType, Shape, AffectsFilter

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
        source: Optional[str] = None,
    ) -> "ValidationResult":
        """Create a result indicating the action is denied."""
        return ValidationResult(
            allowed=False,
            reason=reason,
            blocking_effect_ids=effect_ids or [],
            blocking_modifier_ids=modifier_ids or [],
            blocked_by_source=source,
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
        context: Optional[Dict[str, Any]] = None,
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
                        source=mod.source_id,
                    )

        return ValidationResult.allow()

    def can_move(
        self,
        state: "GameState",
        unit_id: str,
        distance: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Can unit move 'distance' spaces?
        Checks: PREVENT_MOVEMENT status, movement restriction effects.
        """
        context = context or {}

        # Check prevention first
        action_result = self.can_perform_action(
            state, unit_id, ActionType.MOVEMENT, context
        )
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

    def can_be_placed(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        destination: Optional["Hex"] = None,
        context: Optional[Dict[str, Any]] = None,
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

        unit = state.get_unit(UnitID(unit_id))
        actor = state.get_unit(UnitID(actor_id))

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
            if (
                str(mod.target_id) == str(unit_id)
                and mod.status_tag == "PREVENT_PLACEMENT"
            ):
                if self._is_modifier_active(mod, state):
                    # Check if actor is blocked by this modifier
                    if self._actor_blocked_by_modifier(mod, actor, unit, state):
                        return ValidationResult.deny(
                            reason="Unit cannot be placed",
                            modifier_ids=[mod.id],
                            source=mod.source_id,
                        )

        # Check spatial placement prevention effects (ActiveEffects)
        unit_loc = state.entity_locations.get(BoardEntityID(unit_id))
        if not unit_loc:
            # Unit not on board - only check destination-based effects (future)
            return ValidationResult.allow()

        for effect in state.active_effects:
            if effect.effect_type != EffectType.PLACEMENT_PREVENTION:
                continue
            if not self._is_effect_active(effect, state):
                continue
            if not self._is_in_scope(effect, unit_id, unit_loc, state):
                continue

            # Check if this actor's actions are blocked
            if self._actor_blocked_by_effect(effect, actor, unit, state):
                return ValidationResult.deny(
                    reason="Placement prevented by area effect",
                    effect_ids=[effect.id],
                    source=effect.source_id,
                )

        return ValidationResult.allow()

    def can_be_pushed(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """Can unit_id be pushed by actor_id?"""
        return self.can_be_placed(state, unit_id, actor_id, None, context)

    def can_be_swapped(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """Can unit_id be swapped by actor_id?"""
        return self.can_be_placed(state, unit_id, actor_id, None, context)

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _is_modifier_active(
        self, mod: Union[Modifier, ActiveEffect], state: "GameState"
    ) -> bool:
        """
        Check if modifier is currently active.
        Order matters: (1) Check PASSIVE first, (2) Card state, (3) Duration timing.
        """
        # PASSIVE effects are ALWAYS active
        if mod.duration == DurationType.PASSIVE:
            return True

        # Card-based effects require source card to be in played state
        if mod.source_card_id:
            if not self._is_card_in_played_state(
                state, mod.source_id, mod.source_card_id
            ):
                return False

        # Check temporal duration
        if mod.duration == DurationType.THIS_TURN:
            return (
                state.turn == mod.created_at_turn
                and state.round == mod.created_at_round
            )

        if mod.duration == DurationType.NEXT_TURN:
            # Active on the turn AFTER creation (within same round only!)
            if state.round == mod.created_at_round:
                return state.turn == mod.created_at_turn + 1
            return False  # Cross-round NEXT_TURN never activates

        if mod.duration == DurationType.THIS_ROUND:
            return state.round == mod.created_at_round

        return False

    def _is_effect_active(self, effect: ActiveEffect, state: "GameState") -> bool:
        """Check if effect is currently active based on card state and duration."""
        # Reuse modifier logic as fields are compatible/similar for activation
        # Cast to Any to bypass type checker if needed, but structure is same
        return self._is_modifier_active(effect, state)

    def _is_card_in_played_state(
        self, state: "GameState", hero_id: str, card_id: str
    ) -> bool:
        """
        Check if a card is currently in the hero's played state.
        A card is "played" if it's in hero.played_cards OR hero.current_turn_card.
        """
        hero = state.get_hero(HeroID(hero_id))
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
        self, mod: Modifier, actor: Any, target: Any, state: "GameState"
    ) -> bool:
        """Determine if actor is blocked by this modifier."""
        # For now, modifiers on a target block all enemy actions
        if not actor or not target:
            return False

        actor_team = getattr(actor, "team", None)
        target_team = getattr(target, "team", None)

        if actor_team is None or target_team is None:
            return False

        # Enemy trying to displace protected unit
        return actor_team != target_team

    def _is_in_scope(
        self,
        effect: ActiveEffect,
        target_id: str,
        target_hex: "Hex",
        state: "GameState",
    ) -> bool:
        """Check if target is within effect's spatial and relational scope."""
        # Check relational filter (enemy/friendly)
        if not self._matches_affects_filter(effect, target_id, state):
            return False

        # Check spatial shape
        return self._hex_in_scope(effect, target_hex, state)

    def _hex_in_scope(
        self, effect: ActiveEffect, hex: "Hex", state: "GameState"
    ) -> bool:
        """Check if a hex is within effect's spatial scope."""
        scope = effect.scope

        if scope.shape == Shape.GLOBAL:
            return True

        origin = self._get_origin_hex(effect, state)
        if not origin:
            return False

        if scope.shape == Shape.POINT:
            return hex == origin

        if scope.shape == Shape.ADJACENT:
            return origin.distance(hex) == 1

        if scope.shape == Shape.RADIUS:
            return origin.distance(hex) <= scope.range

        if scope.shape == Shape.LINE:
            # Check if hex is on the line from origin in specified direction
            if scope.direction is None:
                return False
            return origin.is_straight_line(hex) and origin.distance(hex) <= scope.range

        if scope.shape == Shape.ZONE:
            # Check if both are in same zone
            origin_zone = self._get_zone_for_hex(origin, state)
            target_zone = self._get_zone_for_hex(hex, state)
            if origin_zone is None or target_zone is None:
                return False
            return origin_zone == target_zone

        return False

    def _get_origin_hex(
        self, effect: ActiveEffect, state: "GameState"
    ) -> Optional["Hex"]:
        """Resolve origin point for spatial effects."""
        if effect.scope.origin_hex:
            return effect.scope.origin_hex

        origin_id = effect.scope.origin_id or effect.source_id
        return state.entity_locations.get(BoardEntityID(origin_id))

    def _get_zone_for_hex(self, hex: "Hex", state: "GameState") -> Optional[str]:
        """Get zone ID containing this hex."""
        for zone_id, zone in state.board.zones.items():
            if hex in zone.hexes:
                return zone_id
        return None

    def _matches_affects_filter(
        self, effect: ActiveEffect, target_id: str, state: "GameState"
    ) -> bool:
        """Check if target matches the relational filter."""
        affects = effect.scope.affects

        if affects == AffectsFilter.ALL_UNITS:
            return True

        source = state.get_entity(BoardEntityID(effect.source_id))
        target = state.get_entity(BoardEntityID(target_id))

        if not source or not target:
            return False

        # Get teams
        source_team = getattr(source, "team", None)
        target_team = getattr(target, "team", None)

        if source_team is None or target_team is None:
            return affects == AffectsFilter.ALL_UNITS

        is_same_team = source_team == target_team
        is_self = effect.source_id == target_id

        # Check unit type
        from goa2.domain.models import Hero, Minion

        is_hero = isinstance(target, Hero)
        is_minion = isinstance(target, Minion)

        if affects == AffectsFilter.SELF:
            return is_self
        if affects == AffectsFilter.ENEMY_UNITS:
            return not is_same_team
        if affects == AffectsFilter.FRIENDLY_UNITS:
            return is_same_team and not is_self
        if affects == AffectsFilter.ENEMY_HEROES:
            return not is_same_team and is_hero
        if affects == AffectsFilter.FRIENDLY_HEROES:
            return is_same_team and not is_self and is_hero
        if affects == AffectsFilter.ALL_HEROES:
            return is_hero
        if affects == AffectsFilter.ALL_MINIONS:
            return is_minion

        return False

    def _actor_blocked_by_effect(
        self, effect: ActiveEffect, actor: Any, target: Any, state: "GameState"
    ) -> bool:
        """Determine if actor is blocked by this effect."""
        if not actor:
            return False

        actor_team = getattr(actor, "team", None)
        source = state.get_entity(BoardEntityID(effect.source_id))
        source_team = getattr(source, "team", None) if source else None

        if actor_team is None or source_team is None:
            return False

        is_actor_enemy_of_source = actor_team != source_team
        is_actor_self = actor.id == effect.source_id

        if effect.blocks_self and is_actor_self:
            return True
        if effect.blocks_enemy_actors and is_actor_enemy_of_source:
            return True
        if (
            effect.blocks_friendly_actors
            and not is_actor_enemy_of_source
            and not is_actor_self
        ):
            return True

        return False
