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
    # Renamed internal storage for masking logic
    real_tier: CardTier = Field(alias="tier")
    real_color: Optional[CardColor] = Field(alias="color")
    real_primary_action: Optional[ActionType] = Field(alias="primary_action")
    real_secondary_actions: Dict[ActionType, int] = Field(default_factory=dict, alias="secondary_actions")
    real_effect_id: str = Field(alias="effect_id")
    real_effect_text: str = Field(alias="effect_text")
    
    initiative: int
    
    # State Management
    state: CardState = CardState.DECK
    is_facedown: bool = True # Default is Hidden

    # Range/Targeting Logic
    is_ranged: bool = False
    range_value: Optional[int] = Field(None, description="Max distance if ranged")
    radius_value: Optional[int] = Field(None, description="Area of effect size (1 = adjacent)")
    
    # Item (Passive bonuses when equipped as item)
    item: Optional[StatType] = None
    
    # Runtime metadata
    metadata: Dict[str, Any] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.metadata is None:
            self.metadata = {}
    
    # -- Property Masking --
    
    @property
    def tier(self) -> CardTier:
        if self.is_facedown: return CardTier.UNTIERED
        return self.real_tier
        
    @property
    def color(self) -> Optional[CardColor]:
        if self.is_facedown: return None
        return self.real_color

    @property
    def primary_action(self) -> Optional[ActionType]:
        if self.is_facedown: return None
        return self.real_primary_action

    @property
    def secondary_actions(self) -> Dict[ActionType, int]:
        if self.is_facedown: return {}
        return self.real_secondary_actions

    @property
    def effect_id(self) -> Optional[str]:
        if self.is_facedown: return None
        return self.real_effect_id

    @property
    def effect_text(self) -> str:
        if self.is_facedown: return ""
        return self.real_effect_text

    class Config:
        frozen = False
        populate_by_name = True
    
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
        Use REAL fields to validate definition.
        """
        color = self.real_color
        tier = self.real_tier
        
        # If optional fields are None (e.g. invalid init), skip or let Pydantic handle required check?
        # Pydantic ensures required fields are present unless Optional.
        # CardTier is required. Color is required (in valid init).
        # But 'real_color' is Optional in definition above to satisfy type checker if aliases return None?
        # Actually Field(alias="color") means it expects "color" input.
        # If input is provided, it is set.
        
        if color is None: return self # Allow partial init? Or crash? strict validation.

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
        if ActionType.HOLD not in self.real_secondary_actions:
            self.real_secondary_actions[ActionType.HOLD] = 0
        return self

    @model_validator(mode='after')
    def ensure_fast_travel_if_applicable(self) -> Card:
        if not ActionType.FAST_TRAVEL in self.real_secondary_actions:
            if self.real_primary_action == ActionType.MOVEMENT or ActionType.MOVEMENT in self.real_secondary_actions:
                self.real_secondary_actions[ActionType.FAST_TRAVEL] = 0
        return self

    @model_validator(mode='after')
    def ensure_clear_if_applicable(self) -> Card:
        if not ActionType.CLEAR in self.real_secondary_actions:
            if self.real_primary_action == ActionType.ATTACK or ActionType.ATTACK in self.real_secondary_actions:
                self.real_secondary_actions[ActionType.CLEAR] = 0
        return self
