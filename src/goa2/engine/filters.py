from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, List, Any, Literal
from pydantic import BaseModel, Field

from goa2.domain.state import GameState
from goa2.domain.models import TeamColor, Minion, Hero, Unit
from goa2.domain.hex import Hex
from goa2.domain.types import UnitID

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
        
        origin_hex = state.unit_locations.get(origin_uid)
        if not origin_hex: return False
        
        target_hex = None
        if isinstance(candidate, Hex):
            target_hex = candidate
        elif isinstance(candidate, str): # UnitID
            target_hex = state.unit_locations.get(candidate)
            
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
        
        actor = state.get_unit(actor_id)
        target = state.get_unit(candidate) if isinstance(candidate, str) else None
        
        if not actor or not target: 
             print(f"TeamFilter: Missing actor ({actor}) or target ({target}) for {candidate}")
             return False
        
        if self.relation == "SELF":
            return actor.id == target.id
            
        is_same_team = (actor.team == target.team)
        
        if self.relation == "FRIENDLY":
            return is_same_team and (actor.id != target.id)
        elif self.relation == "ENEMY":
            res = not is_same_team
            if not res: print(f"TeamFilter: {actor.team} vs {target.team} is not ENEMY")
            return res
            
        return False

class UnitTypeFilter(FilterCondition):
    type: str = "unit_type_filter"
    unit_type: Literal["HERO", "MINION"]

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        unit = state.get_unit(candidate) if isinstance(candidate, str) else None
        if not unit: return False
        
        if self.unit_type == "HERO":
            return isinstance(unit, Hero)
        elif self.unit_type == "MINION":
            return isinstance(unit, Minion)
        return False

class AdjacencyFilter(FilterCondition):
    """
    Requires the target to be adjacent to a unit matching specific tags.
    E.g. "Adjacent to a Friendly Hero"
    """
    type: str = "adjacency_filter"
    target_tags: List[str] # ["FRIENDLY", "HERO"]
    
    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # 1. Determine location of candidate
        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.unit_locations.get(candidate)
            
        if not cand_hex: return False
        
        # 2. Check neighbors
        neighbors = cand_hex.neighbors()
        
        for n in neighbors:
            # Check who is at neighbor n
            tile = state.board.get_tile(n)
            if not tile or not tile.occupant_id:
                continue
                
            occupant = state.get_unit(tile.occupant_id)
            if not occupant: continue
            
            # 3. Check tags
            # We construct a mock context to reuse other filters? 
            # Or just hardcode common tags here? 
            # Reusing filters is cleaner but circular.
            # Let's do manual check for now for simplicity.
            
            actor_id = state.current_actor_id
            actor = state.get_unit(actor_id)
            
            matches = True
            for tag in self.target_tags:
                if tag == "FRIENDLY":
                    if not actor or occupant.team != actor.team or occupant.id == actor.id: matches = False
                elif tag == "ENEMY":
                    if not actor or occupant.team == actor.team: matches = False
                elif tag == "HERO":
                    if not isinstance(occupant, Hero): matches = False
                elif tag == "MINION":
                    if not isinstance(occupant, Minion): matches = False
            
            if matches:
                return True
                
        return False
