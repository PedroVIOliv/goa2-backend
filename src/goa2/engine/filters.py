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
    origin_id: Optional[str] = None # If None, uses current_actor_id from state

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        origin_uid = self.origin_id if self.origin_id else state.current_actor_id
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