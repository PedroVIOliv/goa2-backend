"""ActiveEffect model and related enums for spatial/behavioral effects."""

from __future__ import annotations
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from goa2.domain.models.modifier import DurationType
from goa2.domain.models.enums import ActionType, StatType
from goa2.domain.hex import Hex


class EffectType(str, Enum):
    """Categories of spatial/behavioral effects."""

    PLACEMENT_PREVENTION = "placement_prevention"  # Magnetic Dagger
    MOVEMENT_ZONE = "movement_zone"  # Slippery Ground
    TARGET_PREVENTION = "target_prevention"  # Smoke Bomb
    AREA_STAT_MODIFIER = "area_stat_modifier"  # Aura effects


class AffectsFilter(str, Enum):
    """Who is affected by this effect."""

    SELF = "self"
    FRIENDLY_UNITS = "friendly_units"
    FRIENDLY_HEROES = "friendly_heroes"
    ENEMY_UNITS = "enemy_units"
    ENEMY_HEROES = "enemy_heroes"
    ALL_UNITS = "all_units"
    ALL_HEROES = "all_heroes"
    ALL_MINIONS = "all_minions"


class Shape(str, Enum):
    """Spatial shape of effect area."""

    POINT = "point"  # Single target (specified by target_id)
    RADIUS = "radius"  # Circle around origin
    ADJACENT = "adjacent"  # Distance 1 only
    LINE = "line"  # Straight line in direction
    ZONE = "zone"  # Entire zone
    GLOBAL = "global"  # Entire board


class EffectScope(BaseModel):
    """Defines the spatial and relational scope of an effect."""

    shape: Shape
    range: int = 0  # For RADIUS/LINE
    origin_id: Optional[str] = None  # Entity to measure from (defaults to source)
    origin_hex: Optional[Hex] = None  # Fixed location (overrides origin_id)
    affects: AffectsFilter = AffectsFilter.ALL_UNITS
    direction: Optional[int] = None  # 0-5 for hex directions (LINE shape)


class ActiveEffect(BaseModel):
    """
    Represents a spatial or behavioral effect that applies to an area.
    Used for: Magnetic Dagger (placement prevention in radius),
              Slippery Ground (movement restriction in area), etc.
    """

    id: str
    source_id: str  # Hero ID that created this
    source_card_id: Optional[str] = None  # Card ID (if card-based effect)
    effect_type: EffectType

    # Spatial scope
    scope: EffectScope

    # Effect-specific payload
    restrictions: List[ActionType] = Field(
        default_factory=list
    )  # For prevention effects
    stat_type: Optional[StatType] = None  # For AREA_STAT_MODIFIER
    stat_value: int = 0  # Modifier amount
    max_value: Optional[int] = None  # For movement caps
    limit_actions_only: bool = False  # If True, only caps explicit MOVEMENT actions

    # Lifecycle
    duration: DurationType
    created_at_turn: int
    created_at_round: int

    # Actor restriction: whose actions are blocked?
    blocks_enemy_actors: bool = True  # True = enemy actions blocked
    blocks_friendly_actors: bool = False  # True = friendly actions blocked
    blocks_self: bool = False  # True = source's own actions blocked
