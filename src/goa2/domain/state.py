from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional, Tuple
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
    


    # Map State
    active_zone_id: Optional[str] = None # The ID of the current Battle Zone
    
    phase: GamePhase = GamePhase.SETUP

    resolution_step: ResolutionStep = ResolutionStep.NONE
    round: int = 1
    turn: int = 1
    wave_counter: int = 5
    
    # ID of the Hero currently acting (Resolution Phase)
    current_actor_id: Optional[HeroID] = None
    
    # Interaction Stack
    # The top of the stack is the active request waiting for input.
    # Logic: 
    # 1. Action pushes Request.
    # 2. State pauses.
    # 3. Client responds to Request[0].
    # 4. Engine pops Request.
    input_stack: List[InputRequest] = Field(default_factory=list)
    
    @property
    def awaiting_input_type(self) -> InputRequestType:
        """
        Helper to get the current expected input type from the top of the stack.
        Returns NONE if stack is empty.
        """
        if not self.input_stack:
            return InputRequestType.NONE
        return self.input_stack[-1].request_type
    
    # Planning Phase Buffer: HeroID -> Card
    pending_inputs: Dict[HeroID, Card] = Field(default_factory=dict)
    
    # Resolution Phase Queue: List of (HeroID, Card)
    # Ordered by Initiative
    resolution_queue: List[Tuple[HeroID, Card]] = Field(default_factory=list)

    # Dynamic State: Unit ID -> Hex Location
    unit_locations: Dict[UnitID, Hex] = Field(default_factory=dict)

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
        
        # 1. Update Unit Location Mapping
        old_hex = self.unit_locations.get(unit_id)
        self.unit_locations[unit_id] = target_hex
        
        # 2. Update Board Tiles (Grid)
        if old_hex and old_hex in self.board.tiles:
             # Only clear if it was occupied by THIS unit
             current_occ = self.board.tiles[old_hex].occupant_id
             if current_occ and str(current_occ) == str(unit_id):
                 self.board.tiles[old_hex].occupant_id = None
                 
        if target_hex in self.board.tiles:
            # Overwrite? Yes. Caller should validate emptiness if needed.
            self.board.tiles[target_hex].occupant_id = BoardEntityID(str(unit_id))

    def remove_unit(self, unit_id: UnitID):
        """
        Removes a unit from the board (locations and tiles).
        Does NOT remove it from the Team roster.
        """
        if unit_id in self.unit_locations:
            loc = self.unit_locations[unit_id]
            del self.unit_locations[unit_id]
            
            if loc in self.board.tiles:
                current_occ = self.board.tiles[loc].occupant_id
                if current_occ and str(current_occ) == str(unit_id):
                    self.board.tiles[loc].occupant_id = None

    class Config:
        # Pydantic V2 ConfigDict
        arbitrary_types_allowed = True
        
GameState.model_rebuild()
