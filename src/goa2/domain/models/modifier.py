from __future__ import annotations
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from goa2.domain.models.enums import StatType, CardColor
from goa2.domain.types import BoardEntityID

class DurationType(str, Enum):
    THIS_TURN = "THIS_TURN"      # Expires at End of Turn
    NEXT_TURN = "NEXT_TURN"      # Activates next turn, expires at end of that turn
    THIS_ROUND = "THIS_ROUND"    # Expires at End of Round
    PASSIVE = "PASSIVE"          # Permanent (until source is removed)

class Modifier(BaseModel):
    """
    Represents a temporary or passive modification to a unit's stats or capabilities.
    """
    id: str                      # Unique ID for this specific modifier instance
    source_id: str               # ID of the entity/card that created this (e.g., "living_tsunami")
    source_card_id: Optional[str] = None  # Card ID if effect is card-based (for lifecycle tracking)
    target_id: BoardEntityID     # Who is being affected?
    
    # Payload: Either a numeric stat change...
    stat_type: Optional[StatType] = None
    value_mod: int = 0
    
    # ...or a boolean rule override (status tag)
    status_tag: Optional[str] = None

    # Exceptions (e.g., Spell Break "except on Gold cards")
    except_card_colors: List[CardColor] = Field(default_factory=list)
    
    # Lifecycle
    duration: DurationType
    created_at_turn: int
    created_at_round: int