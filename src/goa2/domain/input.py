from typing import Dict, Any, List
from pydantic import BaseModel, Field
from goa2.domain.types import HeroID
from enum import Enum

class InputRequestType(str, Enum):
    NONE = "NONE"
    ACTION_CHOICE = "ACTION_CHOICE"
    MOVEMENT_HEX = "MOVEMENT_HEX"
    DEFENSE_CARD = "DEFENSE_CARD"
    TIE_BREAKER = "TIE_BREAKER"
    # General Purpose for "Select X"
    SELECT_ALLY = "SELECT_ALLY" 
    SELECT_ENEMY = "SELECT_ENEMY"

class InputRequest(BaseModel):
    id: str  # Unique ID for tracking
    player_id: HeroID # WHO must answer
    request_type: InputRequestType # WHAT to answer
    context: Dict[str, Any] = Field(default_factory=dict) # Metadata e.g. valid_hexes

    class Config:
        arbitrary_types_allowed = True
