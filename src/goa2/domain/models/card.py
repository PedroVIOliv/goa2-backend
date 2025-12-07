from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field, model_validator
from .enums import CardTier, CardColor, ActionType, StatType
from .base import GameEntity

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
    secondary_actions: Dict[ActionType, int] = Field(default_factory=dict)
    
    # Range/Targeting Logic
    is_ranged: bool = False
    range_value: Optional[int] = Field(None, description="Max distance if ranged")
    radius_value: Optional[int] = Field(None, description="Area of effect size (1 = adjacent)")
    
    # Item (Passive bonuses when equipped as item)
    item: Optional[StatType] = None
    
    # Text/Logic Hook (References the implementation of the card's effect)
    effect_id: str
    # Text/Logic Readable description
    effect_text: str

    class Config:
        frozen = True

    @model_validator(mode='after')
    def ensure_hold_action(self) -> Card:
        if ActionType.HOLD not in self.secondary_actions:
            self.secondary_actions[ActionType.HOLD] = 0
        return self
