from __future__ import annotations
from typing import Optional, Dict, Any
from pydantic import Field, model_validator, ConfigDict
from .enums import CardTier, CardColor, ActionType, StatType, CardState
from .base import GameEntity


class Card(GameEntity):
    """
    Represents a specific card definition.
    Current state (In Hand, Discarded) is managed by GameState.
    """

    # Renamed internal storage for masking logic
    tier: CardTier = Field(alias="tier")
    color: Optional[CardColor] = Field(alias="color")
    primary_action: Optional[ActionType] = Field(alias="primary_action")
    primary_action_value: Optional[int] = Field(None, alias="primary_action_value")
    secondary_actions: Dict[ActionType, int] = Field(
        default_factory=dict, alias="secondary_actions"
    )
    effect_id: str = Field(alias="effect_id")
    effect_text: str = Field(alias="effect_text")

    initiative: int

    state: CardState = CardState.DECK
    is_facedown: bool = True  # Default is Hidden
    played_this_round: bool = Field(
        default=False,
        description="True if card was played during Planning Phase this round.",
    )

    # Range/Targeting Logic
    is_ranged: bool = False
    range_value: Optional[int] = Field(None, description="Max distance if ranged")
    radius_value: Optional[int] = Field(
        None, description="Area of effect size (1 = adjacent)"
    )

    # Item (Passive bonuses when equipped as item)
    item: Optional[StatType] = None

    # Passive ability usage tracking (reset at turn end)
    passive_uses_this_turn: int = 0

    # Active effect tracking (tapped/sideways in physical game)
    # Access via the `is_active` property — do NOT read/write this field directly.
    is_active_base: bool = Field(
        default=False,
        description="Raw active-effect flag. Use the is_active property instead.",
    )
    enraged_active_override: bool = Field(
        default=False,
        description="Ursafar ultimate (Unbound Fury): when True, is_active always returns True.",
    )

    @property
    def is_active(self) -> bool:
        return self.is_active_base or self.enraged_active_override

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self.is_active_base = value

    metadata: Optional[Dict[str, Any]] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.metadata is None:
            self.metadata = {}

    # -- Masked Values for in-game logic --
    # Use these when resolving game state where hidden info matters.

    @property
    def current_tier(self) -> CardTier:
        if self.is_facedown:
            return CardTier.UNTIERED
        return self.tier

    @property
    def current_color(self) -> Optional[CardColor]:
        if self.is_facedown:
            return None
        return self.color

    @property
    def current_primary_action(self) -> Optional[ActionType]:
        if self.is_facedown:
            return None
        return self.primary_action

    @property
    def current_primary_action_value(self) -> Optional[int]:
        if self.is_facedown:
            return None
        return self.primary_action_value

    @property
    def current_secondary_actions(self) -> Dict[ActionType, int]:
        if self.is_facedown:
            # Hold is always available and not hidden info
            if ActionType.HOLD in self.secondary_actions:
                return {ActionType.HOLD: 0}
            return {}
        return self.secondary_actions

    @property
    def current_effect_id(self) -> Optional[str]:
        if self.is_facedown:
            return None
        return self.effect_id

    @property
    def current_effect_text(self) -> str:
        if self.is_facedown:
            return ""
        return self.effect_text

    @property
    def current_initiative(self) -> int:
        if self.is_facedown:
            return 0
        return self.initiative

    model_config = ConfigDict(frozen=False, populate_by_name=True)

    @property
    def is_basic(self) -> bool:
        return self.tier == CardTier.UNTIERED

    @property
    def is_skill(self) -> bool:
        return self.primary_action == ActionType.SKILL

    @model_validator(mode="after")
    def validate_range_radius_exclusive(self) -> Card:
        """
        Rule: A card has Range OR Radius, not both.
        """
        if self.range_value is not None and self.radius_value is not None:
            raise ValueError("Card cannot have both Range and Radius values.")
        return self

    @model_validator(mode="after")
    def validate_tier_color_match(self) -> Card:
        """
        Enforce strict Color <-> Tier relationship.
        """
        color = self.color
        tier = self.tier

        if color is None:
            return self

        # Case 1: Gold/Silver must be UNTIERED
        if color in (CardColor.GOLD, CardColor.SILVER):
            if tier != CardTier.UNTIERED:
                raise ValueError(
                    f"Card color {color.name} must be UNTIERED, got {tier.name}"
                )

        # Case 2: Red/Blue/Green must be I, II, or III
        elif color in (CardColor.RED, CardColor.BLUE, CardColor.GREEN):
            if tier not in (CardTier.I, CardTier.II, CardTier.III):
                raise ValueError(
                    f"Card color {color.name} must be Tier I, II or III, got {tier.name}"
                )

        # Case 3: Purple must be IV
        elif color == CardColor.PURPLE:
            if tier != CardTier.IV:
                raise ValueError(
                    f"Card color {color.name} must be Tier IV, got {tier.name}"
                )

        return self

    @model_validator(mode="after")
    def ensure_hold_action(self) -> Card:
        if ActionType.HOLD not in self.secondary_actions:
            self.secondary_actions[ActionType.HOLD] = 0
        return self

    @model_validator(mode="after")
    def ensure_fast_travel_if_applicable(self) -> Card:
        if ActionType.FAST_TRAVEL not in self.secondary_actions:
            if (
                self.primary_action == ActionType.MOVEMENT
                or ActionType.MOVEMENT in self.secondary_actions
            ):
                self.secondary_actions[ActionType.FAST_TRAVEL] = 0
        return self

    @model_validator(mode="after")
    def ensure_clear_if_applicable(self) -> Card:
        if ActionType.CLEAR not in self.secondary_actions:
            if (
                self.primary_action == ActionType.ATTACK
                or ActionType.ATTACK in self.secondary_actions
            ):
                self.secondary_actions[ActionType.CLEAR] = 0
        return self

    @model_validator(mode="after")
    def ensure_fast_travel_hold_and_clear_are_never_primary(self) -> Card:
        if self.primary_action in (
            ActionType.FAST_TRAVEL,
            ActionType.HOLD,
            ActionType.CLEAR,
        ):
            raise ValueError("Fast Travel, Hold, and Clear cannot be primary actions.")
        return self

    @model_validator(mode="after")
    def ensure_primary_is_attack_skill_movement_or_defense(self) -> Card:
        if self.primary_action not in (
            ActionType.ATTACK,
            ActionType.SKILL,
            ActionType.MOVEMENT,
            ActionType.DEFENSE,
            ActionType.DEFENSE_SKILL,
        ):
            raise ValueError(
                "Primary action must be Attack, Skill, Movement, Defense, or Defense_Skill."
            )
        return self

    @model_validator(mode="after")
    def ensure_actiontypes_dont_overlap(self) -> Card:
        if self.primary_action in self.secondary_actions:
            raise ValueError("Primary action cannot be in secondary actions.")
        return self

    @model_validator(mode="after")
    def ensure_primary_action_has_value_if_not_skill(self) -> Card:
        if (
            self.primary_action
            not in (ActionType.SKILL, ActionType.DEFENSE_SKILL, ActionType.DEFENSE)
            and self.primary_action_value is None
        ):
            raise ValueError(
                "Primary action must have a value if it is not a Skill, Defense_Skill, or Defense."
            )
        if (
            self.primary_action == ActionType.SKILL
            and self.primary_action_value is not None
        ):
            raise ValueError(
                "Skill primary action must have None as primary_action_value."
            )
        return self

    def get_base_stat_value(self, stat_type: StatType) -> int:
        """
        Retrieves the base value for a given stat from the card.
        Handles mapping from StatType to ActionType logic (Primary/Secondary).
        """
        # 1. Direct Property Stats
        if stat_type == StatType.INITIATIVE:
            return self.current_initiative
        if stat_type == StatType.RANGE:
            return self.range_value or 0
        if stat_type == StatType.RADIUS:
            return self.radius_value or 0

        # 2. Action Stats
        target_action = None
        if stat_type == StatType.MOVEMENT:
            target_action = ActionType.MOVEMENT
        elif stat_type == StatType.ATTACK:
            target_action = ActionType.ATTACK
        elif stat_type == StatType.DEFENSE:
            target_action = ActionType.DEFENSE

        if target_action:
            # Check Primary (including DEFENSE_SKILL for DEFENSE stat)
            if self.current_primary_action == target_action:
                return self.current_primary_action_value or 0
            # Special case: DEFENSE stat also checks DEFENSE_SKILL
            if (
                stat_type == StatType.DEFENSE
                and self.current_primary_action == ActionType.DEFENSE_SKILL
            ):
                return self.current_primary_action_value or 0

            # Check Secondary
            if target_action in self.current_secondary_actions:
                return self.current_secondary_actions[target_action]

        return 0
