from __future__ import annotations
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from .enums import CardTier, CardColor, ActionType

class GameEntity(BaseModel):
    """Base class for anything that has a distinct identity in the game."""
    id: str
    name: str

class Card(GameEntity):
    """
    Represents a specific card definition.
    Current state (In Hand, Discarded) is managed by GameState.
    """
    tier: CardTier
    color: CardColor
    initiative: int
    
    # Action Classification
    primary_action: ActionType
    
    # Range/Targeting Logic
    is_ranged: bool = False
    range_value: Optional[int] = Field(None, description="Max distance if ranged")
    radius_value: Optional[int] = Field(None, description="Area of effect size (1 = adjacent)")
    
    # Item Stats (Passive bonuses when equipped as item)
    # Generic key-value for flexibility e.g. {"attack": 1, "initiative": 1}
    item_bonuses: Dict[str, int] = Field(default_factory=dict)
    
    # Text/Logic Hook (References the implementation of the card's effect)
    effect_id: str

    class Config:
        frozen = True
