from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel
from goa2.domain.models.enums import StatType
from goa2.domain.types import BoardEntityID

class DurationType(str, Enum):
    THIS_TURN = "THIS_TURN"      # Expires at End of Turn
    THIS_ROUND = "THIS_ROUND"    # Expires at End of Round
    PASSIVE = "PASSIVE"          # Permanent (until source is removed)

class Modifier(BaseModel):
    """
    Represents a temporary or passive modification to a unit's stats or capabilities.
    """
    id: str                      # Unique ID for this specific modifier instance
    source_id: str               # ID of the entity/card that created this (e.g., "living_tsunami")
    target_id: BoardEntityID     # Who is being affected?
    
    # Payload: Either a numeric stat change...
    stat_type: Optional[StatType] = None
    value_mod: int = 0
    
    # ...or a boolean rule override (status tag)
    status_tag: Optional[str] = None
    
    # Lifecycle
    duration: DurationType
    created_at_turn: int
    created_at_round: int
