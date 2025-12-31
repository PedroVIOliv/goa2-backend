from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Card, Minion, Hero, Unit, GamePhase, ResolutionStep
from goa2.domain.types import HeroID, CardID, UnitID, BoardEntityID
from goa2.domain.input import InputRequest, InputRequestType

class GameState(BaseModel):
    """
    The Mutable State of the World.
    Contains everything needed to serialize/save/restore the game.
    """
    board: Board
    teams: Dict[TeamColor, Team]
    
    active_zone_id: Optional[str] = None # The ID of the current Battle Zone
    
    phase: GamePhase = GamePhase.SETUP

    resolution_step: ResolutionStep = ResolutionStep.NONE
    round: int = 1
    turn: int = 1
    wave_counter: int = 5
    
    current_actor_id: Optional[HeroID] = None # ID of the Hero currently acting (Resolution Phase)
    
    # The team that currently wins ties (Red or Blue)
    # Flips every time a different-team tie is resolved.
    tie_breaker_team: TeamColor = TeamColor.RED
    
    input_stack: List[InputRequest] = Field(default_factory=list) # The top of the stack is the active request waiting for input.
    # Logic: 
    # 1. Action pushes Request.
    # 2. State pauses.
    # 3. Client responds to Request[0].
    # 4. Engine pops Request.
    execution_stack: List[Any] = Field(default_factory=list) # Stores instances of GameStep (from goa2.engine.steps)
    # Typed as List[Any] to avoid circular imports with steps.py
    
    execution_context: Dict[str, Any] = Field(default_factory=dict) # Stores transient data like "selected_target_id" between steps
    
    pending_inputs: Dict[HeroID, Card] = Field(default_factory=dict) # Planning Phase Buffer: HeroID -> Card
    
    pending_upgrades: Dict[HeroID, int] = Field(default_factory=dict) # Level Up Phase Buffer: HeroID -> Number of upgrades pending
    
    unresolved_hero_ids: List[HeroID] = Field(default_factory=list) # Resolution Phase Tracker: Set of HeroIDs who have not yet acted this turn.
    # We dynamically re-sort this set every step to determine the next actor.
    # Using List for JSON stability, acts as Set.

    unit_locations: Dict[UnitID, Hex] = Field(default_factory=dict) # Dynamic State: Unit ID -> Hex Location

    @property
    def awaiting_input_type(self) -> InputRequestType:
        """
        Helper to get the current expected input type from the top of the stack.
        Returns NONE if stack is empty.
        """
        if not self.input_stack:
            return InputRequestType.NONE
        return self.input_stack[-1].request_type
    
    def get_hero(self, hero_id: HeroID) -> Optional[Hero]:
        """Finds a Hero by ID."""
        for team in self.teams.values():
            for hero in team.heroes:
                if hero.id == hero_id:
                    return hero
        return None

    def get_unit(self, unit_id: UnitID) -> Optional[Unit]:
        """
        Finds a Unit (Hero or Minion) by ID.
        O(N) search across all teams.
        """
        for team in self.teams.values():
            for hero in team.heroes:
                if str(hero.id) == str(unit_id):
                    return hero
            for minion in team.minions:
                 if str(minion.id) == str(unit_id):
                     return minion
        return None

    def move_unit(self, unit_id: UnitID, target_hex: Hex):
        """
        Moves a unit to a target hex, updating both unit_locations and board tiles.
        Clears the old tile's occupant and sets the new tile's occupant.
        """
        from goa2.domain.types import BoardEntityID # Import locally to avoid circular if any, or just use string cast
        
        old_hex = self.unit_locations.get(unit_id)
        self.unit_locations[unit_id] = target_hex
        
        if old_hex:
             old_tile = self.board.get_tile(old_hex)
             # Only clear if it was occupied by THIS unit
             if old_tile and old_tile.occupant_id and str(old_tile.occupant_id) == str(unit_id):
                 old_tile.occupant_id = None
                 
        target_tile = self.board.get_tile(target_hex)
        if target_tile:
            # Overwrite? Yes. Caller should validate emptiness if needed.
            target_tile.occupant_id = BoardEntityID(str(unit_id))

    def remove_unit(self, unit_id: UnitID):
        """
        Removes a unit from the board (locations and tiles).
        Does NOT remove it from the Team roster.
        """
        if unit_id in self.unit_locations:
            loc = self.unit_locations[unit_id]
            del self.unit_locations[unit_id]
            
            tile = self.board.get_tile(loc)
            if tile:
                if tile.occupant_id and str(tile.occupant_id) == str(unit_id):
                    tile.occupant_id = None

    class Config:
        arbitrary_types_allowed = True
        
GameState.model_rebuild()