from typing import Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict
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
    FAST_TRAVEL_DESTINATION = "FAST_TRAVEL_DESTINATION"
    SELECT_ENEMY = "SELECT_ENEMY"
    UPGRADE_CHOICE = "UPGRADE_CHOICE"
    SELECT_UNIT = "SELECT_UNIT"
    SELECT_HEX = "SELECT_HEX"

class InputRequest(BaseModel):
    id: str  # Unique ID for tracking
    player_id: HeroID # WHO must answer
    request_type: InputRequestType # WHAT to answer
    context: Dict[str, Any] = Field(default_factory=dict) # Metadata e.g. valid_hexes

    model_config = ConfigDict(
        arbitrary_types_allowed = True
    )
