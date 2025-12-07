from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Card, Minion
from goa2.engine.phases import GamePhase, ResolutionStep
from goa2.domain.types import HeroID, CardID, UnitID
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

    class Config:
        # Pydantic V2 ConfigDict
        arbitrary_types_allowed = True
        
GameState.model_rebuild()
