from __future__ import annotations
from abc import ABC
from typing import Optional, List, Any, Literal
from pydantic import BaseModel

from goa2.domain.state import GameState
from goa2.domain.models import Minion, Hero, Unit
from goa2.domain.hex import Hex

# -----------------------------------------------------------------------------
# Base Filter
# -----------------------------------------------------------------------------

class FilterCondition(BaseModel, ABC):
    """
    Base class for all selection filters.
    """
    type: str

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        """
        Returns True if the candidate passes the filter.
        Candidate can be a UnitID (str) or a Hex.
        """
        raise NotImplementedError

# -----------------------------------------------------------------------------
# Hex Filters
# -----------------------------------------------------------------------------

class OccupiedFilter(FilterCondition):
    type: str = "occupied_filter"
    is_occupied: bool = False # False = Must be empty, True = Must be occupied

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)
            if not tile: return False
            return tile.is_occupied == self.is_occupied
        return False

class TerrainFilter(FilterCondition):
    type: str = "terrain_filter"
    is_terrain: bool = True

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)
            if not tile: return False
            return tile.is_terrain == self.is_terrain
        return False

class RangeFilter(FilterCondition):
    """
    Checks distance from an origin.
    Origin is usually the current actor, but can be customized.
    """
    type: str = "range_filter"
    max_range: int
    min_range: int = 0
    origin_id: Optional[str] = None # Literal ID
    origin_key: Optional[str] = None # Key in context to find ID

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        origin_uid = None
        
        if self.origin_id:
            origin_uid = self.origin_id
        elif self.origin_key:
            origin_uid = context.get(self.origin_key)
        
        if not origin_uid:
            origin_uid = state.current_actor_id
        
        if not origin_uid: return False
        
        # Use Unified Location
        origin_hex = state.entity_locations.get(origin_uid)
        if not origin_hex: return False
        
        target_hex = None
        if isinstance(candidate, Hex):
            target_hex = candidate
        elif isinstance(candidate, str): # EntityID
            target_hex = state.entity_locations.get(candidate)
            
        if not target_hex: return False
        
        dist = origin_hex.distance(target_hex)
        return self.min_range <= dist <= self.max_range

# -----------------------------------------------------------------------------
# Unit Filters
# -----------------------------------------------------------------------------

class TeamFilter(FilterCondition):
    type: str = "team_filter"
    relation: Literal["FRIENDLY", "ENEMY", "SELF"] 
    # RELATIVE to the actor executing the step

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        actor_id = state.current_actor_id
        if not actor_id: return False
        
        actor = state.get_entity(actor_id)
        target = state.get_entity(candidate) if isinstance(candidate, str) else None
        
        if not actor or not target: 
             # Only warn if strict logic required. For now, fail silently (filter mismatch)
             return False
        
        # Ensure both have 'team' attribute (Tokens might not)
        if not hasattr(actor, 'team') or not hasattr(target, 'team'):
             return False

        if self.relation == "SELF":
            return actor.id == target.id
            
        is_same_team = (actor.team == target.team)
        
        if self.relation == "FRIENDLY":
            return is_same_team and (actor.id != target.id)
        elif self.relation == "ENEMY":
            return not is_same_team
            
        return False

class UnitTypeFilter(FilterCondition):
    type: str = "unit_type_filter"
    unit_type: Literal["HERO", "MINION"]

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        entity = state.get_entity(candidate) if isinstance(candidate, str) else None
        if not entity: return False
        
        if self.unit_type == "HERO":
            return isinstance(entity, Hero)
        elif self.unit_type == "MINION":
            return isinstance(entity, Minion)
        return False

class AdjacencyFilter(FilterCondition):
    """
    Requires the target to be adjacent to a unit matching specific tags.
    E.g. "Adjacent to a Friendly Hero"
    """
    type: str = "adjacency_filter"
    target_tags: List[str] # ["FRIENDLY", "HERO"]
    
    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(candidate)
            
        if not cand_hex: return False
        
        neighbors = cand_hex.neighbors()
        
        for n in neighbors:
            tile = state.board.get_tile(n)
            if not tile or not tile.occupant_id:
                continue
            
            # Use Unified Lookup
            occupant = state.get_entity(tile.occupant_id)
            if not occupant: continue
            
            actor_id = state.current_actor_id
            actor = state.get_entity(actor_id)
            
            matches = True
            for tag in self.target_tags:
                if tag == "FRIENDLY":
                    if not hasattr(occupant, 'team') or not hasattr(actor, 'team'):
                        matches = False
                    elif occupant.team != actor.team or occupant.id == actor.id: 
                        matches = False
                elif tag == "ENEMY":
                    if not hasattr(occupant, 'team') or not hasattr(actor, 'team'):
                         matches = False
                    elif occupant.team == actor.team: 
                        matches = False
                elif tag == "HERO":
                    if not isinstance(occupant, Hero): matches = False
                elif tag == "MINION":
                    if not isinstance(occupant, Minion): matches = False
            
            if matches:
                return True
                
        return False

class ImmunityFilter(FilterCondition):
    """
    Filters out candidates that are Immune.
    """
    type: str = "immunity_filter"
    
    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        from goa2.engine import rules # Import inside to be safe
        target = state.get_entity(candidate) if isinstance(candidate, str) else None
        if not target: return False
        
        # If Immune, it fails the filter (returns False)
        if isinstance(target, Unit):
            return not rules.is_immune(target, state)
        return True # Non-units (Tokens) typically don't have "Immunity" logic yet, so pass default.

class SpawnPointFilter(FilterCondition):
    """
    Filters hexes based on whether they have a spawn point.
    """
    type: str = "spawn_point_filter"
    has_spawn_point: bool = False

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)
            if not tile: return False
            return (tile.spawn_point is not None) == self.has_spawn_point
        return False

class AdjacentSpawnPointFilter(FilterCondition):
    """
    Filters hexes based on proximity to spawn points.
    """
    type: str = "adjacent_spawn_point_filter"
    is_empty: bool = True
    must_not_have: bool = True # True means "not adjacent to", False means "must be adjacent to"

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(candidate)
            
        if not cand_hex: return False
        
        neighbors = cand_hex.neighbors()
        has_adj = False
        for n in neighbors:
            tile = state.board.get_tile(n)
            if tile and tile.spawn_point:
                if self.is_empty:
                    if not tile.is_occupied:
                        has_adj = True
                        break
                else:
                    has_adj = True
                    break
        
        if self.must_not_have:
            return not has_adj
        return has_adj

class AdjacencyToContextFilter(FilterCondition):
    """
    Selects units adjacent to the entity ID stored in a context variable.
    """
    type: str = "adjacency_to_context_filter"
    target_key: str

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:

        target_id = context.get(self.target_key)

        if not target_id: return False

        target_hex = state.entity_locations.get(target_id)

        if not target_hex: return False

        cand_hex = None

        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(candidate)
            if not cand_hex: return False
            # "Check via tile": Ensure both are valid board positions
            if not state.board.is_on_map(target_hex) or not state.board.is_on_map(cand_hex):
                return False
            return cand_hex.distance(target_hex) == 1
class ExcludeIdentityFilter(FilterCondition):
    """
    Excludes specific unit IDs from selection.
    Can exclude self and/or IDs found in context keys.
    """
    type: str = "exclude_identity_filter"
    exclude_self: bool = True
    exclude_keys: List[str] = []
    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str): return True # Only applies to Units (IDs)
        if self.exclude_self:
            if candidate == state.current_actor_id:
                return False
        for key in self.exclude_keys:
            val = context.get(key)
            if val == candidate:
                return False
        return True
class HasEmptyNeighborFilter(FilterCondition):
    """
    Ensures the candidate unit has at least one valid empty neighbor to move to.
    Prevents selecting 'trapped' units for movement effects.
    """
    type: str = "has_empty_neighbor_filter"
    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        cand_hex = None
        if isinstance(candidate, str):
            cand_hex = state.entity_locations.get(candidate)
        elif isinstance(candidate, Hex):
            cand_hex = candidate
        if not cand_hex: return False
        neighbors = cand_hex.neighbors()
        for n in neighbors:
            # Check if hex exists on board
            tile = state.board.get_tile(n)
            if tile and not tile.is_obstacle:
                 return True
        return False
class ForcedMovementByEnemyFilter(FilterCondition):
    """
    Checks if the candidate is protected from forced movement by enemies.
    """
    type: str = "forced_movement_by_enemy_filter"
    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # 1. Check Relation: Is actor an enemy of candidate?
        actor_id = state.current_actor_id
        if not actor_id: return True # Should not happen
        actor = state.get_entity(actor_id)
        target = state.get_entity(candidate) if isinstance(candidate, str) else None
        if not actor or not target: return True
        if not hasattr(actor, 'team') or not hasattr(target, 'team'): return True
        is_enemy = (actor.team != target.team)
        if not is_enemy:
            return True # Filter passes if not an enemy (can move allies unless blocked by something else)
        # 2. Check Status: Does candidate have 'PREVENT_ENEMY_DISPLACEMENT'?
        from goa2.engine.stats import has_status
        if has_status(state, candidate, "PREVENT_ENEMY_DISPLACEMENT"):
            return False # Filter fails (cannot be selected)
        return True
