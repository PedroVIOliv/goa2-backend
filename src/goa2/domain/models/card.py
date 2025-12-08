from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field, model_validator
from .enums import CardTier, CardColor, ActionType, StatType, CardState
from .base import GameEntity

class Card(GameEntity):
    """
    Represents a specific card definition.
    Current state (In Hand, Discarded) is managed by GameState.
    """
    tier: CardTier
    color: CardColor
    initiative: int
    
    # State Management
    state: CardState = CardState.DECK

    # Action Classification
    primary_action: ActionType
    primary_action_value: Optional[int] = None
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
        frozen = False
    
    @property
    def is_basic(self) -> bool:
        return self.tier == CardTier.UNTIERED
    
    @property
    def is_skill(self) -> bool:
        return self.primary_action == ActionType.SKILL

    @model_validator(mode='after')
    def validate_tier_color_match(self) -> Card:
        """
        Enforce strict Color <-> Tier relationship.
        Gold/Silver -> UNTIERED
        Red/Blue/Green -> I, II, III
        Purple -> IV
        """
        color = self.color
        tier = self.tier

        # Case 1: Gold/Silver must be UNTIERED
        if color in (CardColor.GOLD, CardColor.SILVER):
            if tier != CardTier.UNTIERED:
                raise ValueError(f"Card color {color.name} must be UNTIERED, got {tier.name}")
        
        # Case 2: Red/Blue/Green must be I, II, or III
        elif color in (CardColor.RED, CardColor.BLUE, CardColor.GREEN):
            if tier not in (CardTier.I, CardTier.II, CardTier.III):
                raise ValueError(f"Card color {color.name} must be Tier I, II or III, got {tier.name}")

        # Case 3: Purple must be IV
        elif color == CardColor.PURPLE:
            if tier != CardTier.IV:
                raise ValueError(f"Card color {color.name} must be Tier IV, got {tier.name}")
        
        return self

    @model_validator(mode='after')
    def ensure_hold_action(self) -> Card:
        if ActionType.HOLD not in self.secondary_actions:
            self.secondary_actions[ActionType.HOLD] = 0
        return self

    @model_validator(mode='after')
    def ensure_fast_travel_if_applicable(self) -> Card:
        if not ActionType.FAST_TRAVEL in self.secondary_actions:
            if self.primary_action == ActionType.MOVEMENT or ActionType.MOVEMENT in self.secondary_actions:
                self.secondary_actions[ActionType.FAST_TRAVEL] = 0
        return self

    @model_validator(mode='after')
    def ensure_clear_if_applicable(self) -> Card:
        if not ActionType.CLEAR in self.secondary_actions:
            if self.primary_action == ActionType.ATTACK or ActionType.ATTACK in self.secondary_actions:
                self.secondary_actions[ActionType.CLEAR] = 0
        return self
