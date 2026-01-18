"""Validation service and result types for effect system."""

from __future__ import annotations
from typing import List, Optional, Dict, Any, TYPE_CHECKING, Union, TypedDict

from pydantic import BaseModel, Field

from goa2.domain.types import BoardEntityID, UnitID, HeroID
from goa2.domain.models import Card
from goa2.domain.models.enums import ActionType, CardColor, CardState
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    Shape,
    AffectsFilter,
    DurationType,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.hex import Hex

from goa2.engine.topology import get_topology_service


class ValidationContext(TypedDict, total=False):
    """Context data passed to validation service."""

    card: Optional[Card]
    current_card_id: Optional[str]
    defense_value: Optional[int]
    skipped_respawn: Optional[bool]
    selection: Any  # Default output for SelectStep
    confirmation: Optional[bool]  # Default output for AskConfirmationStep
    # Allow arbitrary keys for now to maintain compatibility with legacy dicts
    # until strict typing is enforced everywhere
    __extra_items__: Any


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
        context: Optional[Union[Dict[str, Any], ValidationContext]] = None,
    ) -> ValidationResult:
        """
        Can actor perform this action type?
        Checks: PREVENT_MOVEMENT, PREVENT_ATTACK, PREVENT_SKILL, etc.
        """
        context = context or {}

        # Helper to check exceptions
        def matches_exception(exceptions: List[CardColor]) -> bool:
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
        state: "GameState",
        unit_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Can unit perform Fast Travel?
        Checks: PREVENT_FAST_TRAVEL status.
        """
        return self.can_perform_action(state, unit_id, ActionType.FAST_TRAVEL, context)

    def can_repeat_action(
        self,
        state: "GameState",
        actor_id: str,
        context: Optional[Dict[str, Any]] = None,
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
                if not self._is_effect_active(effect, state):
                    continue
                if ActionType.SKILL not in effect.restrictions:
                    # SKILL is a proxy for action repeat prevention
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

    def can_move(
        self,
        state: "GameState",
        unit_id: str,
        distance: int,
        context: Optional[Dict[str, Any]] = None,
        is_movement_action: bool = False,
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

    def can_be_targeted(
        self,
        state: "GameState",
        actor_id: str,
        target_id: str,
        context: Optional[Dict[str, Any]] = None,
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

            # Is the blocker on the segment between actor and target?
            # exclusive=True means the blocker cannot be ON the actor or ON the target
            # (though normally tokens share space, Smoke Bomb on self doesn't block self-targeting usually,
            # but standard rule: "between that enemy hero and their target")
            if blocker_hex.is_on_segment(actor_loc, target_loc, exclusive=True):
                return ValidationResult.deny(
                    reason="Line of sight blocked",
                    effect_ids=[effect.id],
                    source=effect.source_id,
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

        Supports both Units (Heroes, Minions) and Tokens.

        Args:
            unit_id: The entity being moved/placed (unit or token)
            actor_id: The hero performing the action
            destination: Target hex (optional, for destination-specific checks)
        """
        context = context or {}

        # Use get_entity() to support both Units and Tokens
        entity = state.get_entity(BoardEntityID(unit_id))
        actor = state.get_entity(BoardEntityID(actor_id))

        if not entity:
            return ValidationResult.deny("Entity not found")

        # Destination validation (if provided)
        if destination:
            tile = state.board.get_tile(destination)
            if not tile:
                return ValidationResult.deny("Destination not on board")
            if tile.is_occupied:
                return ValidationResult.deny("Destination occupied")

        # Check spatial placement prevention effects (ActiveEffects)
        entity_loc = state.entity_locations.get(BoardEntityID(unit_id))
        if not entity_loc:
            # Entity not on board - only check destination-based effects (future)
            return ValidationResult.allow()

        for effect in state.active_effects:
            if effect.effect_type != EffectType.PLACEMENT_PREVENTION:
                continue
            if not self._is_effect_active(effect, state):
                continue
            if not self._is_in_scope(effect, unit_id, entity_loc, state):
                continue

            # Check if this actor's actions are blocked
            # Note: _actor_blocked_by_effect uses getattr for team, so it's token-safe
            if self._actor_blocked_by_effect(effect, actor, entity, state):
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

    def _is_effect_active(self, effect: ActiveEffect, state: "GameState") -> bool:
        """
        Check if effect is currently active.
        Order matters: (1) Check PASSIVE first, (2) is_active flag, (3) Duration timing.
        """
        # PASSIVE effects are ALWAYS active (no is_active check needed)
        if effect.duration == DurationType.PASSIVE:
            return True

        # Card-based effects use explicit is_active flag
        # This flag is set to True when card resolves, False when card leaves play or goes facedown
        if effect.source_card_id:
            if not effect.is_active:
                return False

        # Check temporal duration
        if effect.duration == DurationType.THIS_TURN:
            return (
                state.turn == effect.created_at_turn
                and state.round == effect.created_at_round
            )

        if effect.duration == DurationType.NEXT_TURN:
            # Active on the turn AFTER creation (within same round only!)
            if state.round == effect.created_at_round:
                return state.turn == effect.created_at_turn + 1
            return False  # Cross-round NEXT_TURN never activates

        if effect.duration == DurationType.THIS_ROUND:
            return state.round == effect.created_at_round

        return False

    def _is_card_in_played_state(
        self, state: "GameState", hero_id: str, card_id: str
    ) -> bool:
        """
        Check if a card's active effects should be active.

        Per game rules, active effects are cancelled when:
        - The card leaves the played area (state != RESOLVED)
        - The card is turned facedown

        Effects are created during card resolution (UNRESOLVED state) but only
        become active once the card moves to RESOLVED at turn end. This works
        because effects only matter starting from the next player's turn.
        """
        hero = state.get_hero(HeroID(hero_id))
        if not hero:
            return False

        # Find the card in played_cards (the only place RESOLVED cards live)
        for card in hero.played_cards:
            if card.id == card_id:
                # Card must be RESOLVED and face-up for effects to be active
                return card.state == CardState.RESOLVED and not card.is_facedown

        return False

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
        """Check if a hex is within effect's spatial scope (topology-aware)."""
        scope = effect.scope

        origin = self._get_origin_hex(effect, state)
        if not origin and scope.shape != Shape.GLOBAL:
            return False

        # Use TopologyService for consolidated, topology-aware scope checking
        topology = get_topology_service()
        return topology.hex_in_scope(
            origin if origin else hex,  # For GLOBAL, origin doesn't matter
            hex,
            scope.shape,
            scope.range,
            state,
            scope.direction,
        )

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
