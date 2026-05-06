from __future__ import annotations

from typing import TYPE_CHECKING, Any

from goa2.domain.models.effect import ActiveEffect, AffectsFilter, DurationType, Shape
from goa2.domain.models.enums import CardState
from goa2.domain.types import BoardEntityID, HeroID
from goa2.engine.topology import get_topology_service

if TYPE_CHECKING:
    from goa2.domain.hex import Hex
    from goa2.domain.state import GameState


class EffectValidationMixin:
    def _is_effect_active(self, effect: ActiveEffect, state: GameState) -> bool:
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
            return state.turn == effect.created_at_turn and state.round == effect.created_at_round

        if effect.duration == DurationType.NEXT_TURN:
            # Active on the turn AFTER creation (within same round only!)
            if state.round == effect.created_at_round:
                return state.turn == effect.created_at_turn + 1
            return False  # Cross-round NEXT_TURN never activates

        if effect.duration == DurationType.THIS_ROUND:
            return state.round == effect.created_at_round

        return False

    def _is_card_in_played_state(self, state: GameState, hero_id: str, card_id: str) -> bool:
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
            if card and card.id == card_id:
                # Card must be RESOLVED and face-up for effects to be active
                return card.state == CardState.RESOLVED and not card.is_facedown

        return False

    def _is_in_scope(
        self,
        effect: ActiveEffect,
        target_id: str,
        target_hex: Hex,
        state: GameState,
    ) -> bool:
        """Check if target is within effect's spatial and relational scope."""
        # Check relational filter (enemy/friendly)
        if not self._matches_affects_filter(effect, target_id, state):
            return False

        # Check spatial shape
        return self._hex_in_scope(effect, target_hex, state)

    def _hex_in_scope(self, effect: ActiveEffect, hex: Hex, state: GameState) -> bool:
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

    def _get_origin_hex(self, effect: ActiveEffect, state: GameState) -> Hex | None:
        """Resolve origin point for spatial effects."""
        if effect.scope.origin_hex:
            return effect.scope.origin_hex

        origin_id = effect.scope.origin_id or effect.source_id
        return state.entity_locations.get(BoardEntityID(origin_id))

    def _get_zone_for_hex(self, hex: Hex, state: GameState) -> str | None:
        """Get zone ID containing this hex."""
        for zone_id, zone in state.board.zones.items():
            if hex in zone.hexes:
                return zone_id
        return None

    def _matches_affects_filter(
        self, effect: ActiveEffect, target_id: str, state: GameState
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
        if affects == AffectsFilter.SELF_AND_FRIENDLY_HEROES:
            return is_same_team and is_hero
        if affects == AffectsFilter.ALL_HEROES:
            return is_hero
        if affects == AffectsFilter.ALL_MINIONS:
            return is_minion

        return False

    def _actor_blocked_by_effect(
        self, effect: ActiveEffect, actor: Any, target: Any, state: GameState
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
        if effect.blocks_friendly_actors and not is_actor_enemy_of_source and not is_actor_self:
            return True

        return False
