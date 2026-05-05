from __future__ import annotations
from typing import Any, Dict, Optional, TYPE_CHECKING

from goa2.domain.types import BoardEntityID
from goa2.domain.models.effect import EffectType
from goa2.engine.topology import get_topology_service

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.hex import Hex


class TerrainValidationMixin:
        def is_obstacle_for_actor(
            self,
            state: "GameState",
            hex_pos: "Hex",
            actor_id: Optional[str] = None,
            context: Optional[Dict[str, Any]] = None,
        ) -> bool:
            """
            Context-aware obstacle check that accounts for STATIC_BARRIER effects.

            Returns True if the hex is an obstacle for the given actor.
            This includes both:
            1. Base obstacle status (terrain/occupied)
            2. Dynamic obstacle status from STATIC_BARRIER effects

            Static Barrier logic (Wasp):
            - If acting enemy hero is OUTSIDE barrier radius -> hexes INSIDE radius are obstacles
            - If acting enemy hero is INSIDE barrier radius -> hexes OUTSIDE radius are obstacles
            """
            tile = state.board.get_tile(hex_pos)

            # Base obstacle check (terrain/occupied)
            if tile.is_obstacle:
                return True

            # Check STATIC_BARRIER effects
            if actor_id is None:
                actor_id = str(state.current_actor_id) if state.current_actor_id else None

            if not actor_id:
                return False  # No actor context, can't check barrier effects

            # Get actor entity and verify it's an enemy hero
            from goa2.domain.models import Hero

            actor = state.get_entity(BoardEntityID(actor_id))
            if not actor or not isinstance(actor, Hero):
                return False  # Static Barrier only affects enemy heroes as actors

            for effect in state.active_effects:
                if effect.effect_type != EffectType.STATIC_BARRIER:
                    continue
                if not self._is_effect_active(effect, state):
                    continue

                # Only affects enemy actors
                source = state.get_entity(BoardEntityID(effect.source_id))
                if not source:
                    continue

                actor_team = getattr(actor, "team", None)
                source_team = getattr(source, "team", None)

                if actor_team is None or source_team is None:
                    continue
                if actor_team == source_team:
                    continue  # Friendly actors not affected

                # Get barrier origin position
                origin_id = effect.barrier_origin_id or effect.source_id
                origin_hex = state.entity_locations.get(BoardEntityID(origin_id))
                if not origin_hex:
                    continue

                # Get actor position
                actor_hex = state.entity_locations.get(BoardEntityID(actor_id))
                if not actor_hex:
                    continue

                # Calculate distances using topology-aware distance
                topology = get_topology_service()
                actor_dist = topology.distance(origin_hex, actor_hex, state)
                hex_dist = topology.distance(origin_hex, hex_pos, state)

                # Apply barrier logic:
                # Actor OUTSIDE radius -> hexes INSIDE radius are obstacles
                # Actor INSIDE radius -> hexes OUTSIDE radius are obstacles
                actor_inside = actor_dist <= effect.barrier_radius
                hex_inside = hex_dist <= effect.barrier_radius

                if actor_inside != hex_inside:
                    return True  # This hex is an obstacle for this actor

            return False

        def is_passable_token(self, state: "GameState", hex_pos: "Hex") -> bool:
            """Check if a hex contains a passable token (traversable but not landable)."""
            tile = state.board.get_tile(hex_pos)
            if not tile or not tile.occupant_id:
                return False
            occupant_id = BoardEntityID(str(tile.occupant_id))
            entity = state.get_entity(occupant_id)
            if entity:
                from goa2.domain.models.token import Token

                return isinstance(entity, Token) and entity.is_passable
            for tokens in state.token_pool.values():
                for token in tokens:
                    if BoardEntityID(str(token.id)) == occupant_id:
                        return token.is_passable
            return False

        def is_terrain_hex(
            self,
            state: "GameState",
            hex_pos: "Hex",
        ) -> bool:
            """
            Check if a hex counts as terrain, accounting for PETRIFY effects.
            Returns True if the hex is terrain (static or from PETRIFY effects).
            """
            tile = state.board.get_tile(hex_pos)
            if not tile:
                return False

            if tile.is_terrain:
                return True

            occupant_id = tile.occupant_id
            if not occupant_id:
                return False

            for effect in state.active_effects:
                if effect.effect_type != EffectType.PETRIFY:
                    continue
                if not self._is_effect_active(effect, state):
                    continue
                # For PETRIFY, check if the OCCUPANT is in scope, not if the hex is in scope
                # Get the occupant's position to check against effect's spatial radius
                occupant_loc = state.entity_locations.get(BoardEntityID(str(occupant_id)))
                if not occupant_loc:
                    return False
                if self._is_in_scope(effect, str(occupant_id), occupant_loc, state):
                    return True

            return False
