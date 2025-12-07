from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor
from goa2.engine.phases import GamePhase, ResolutionStep

class GameState(BaseModel):
    """
    The Mutable State of the World.
    Contains everything needed to serialize/save/restore the game.
    """
    board: Board
    teams: Dict[TeamColor, Team]
    
    phase: GamePhase = GamePhase.SETUP
    resolution_step: ResolutionStep = ResolutionStep.NONE
    round: int = 1
    
    # ID of the Hero currently acting (Resolution Phase)
    current_actor_id: Optional[str] = None
    
    # The queue of Cards to be resolved in the current turn.
    # We might need a stricter definition of 'ResolvedCard' wrapper
    # that includes (Card, OwnerHeroID, Initiative).
    # For now, placeholder.
    # resolution_queue: List[Any] = Field(default_factory=list)

    class Config:
        # Pydantic V2 ConfigDict
        arbitrary_types_allowed = True
