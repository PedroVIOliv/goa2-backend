"""ActiveEffect model and related enums for spatial/behavioral effects."""

from __future__ import annotations
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from goa2.domain.models.enums import ActionType, StatType, CardColor, DisplacementType
from goa2.domain.models.marker import MarkerType
from goa2.domain.hex import Hex


class DurationType(str, Enum):
    THIS_TURN = "THIS_TURN"  # Expires at End of Turn
    NEXT_TURN = "NEXT_TURN"  # Activates next turn, expires at end of that turn
    THIS_ROUND = "THIS_ROUND"  # Expires at End of Round
    PASSIVE = "PASSIVE"  # Permanent (until source is removed)


class EffectType(str, Enum):
    """Categories of spatial/behavioral effects."""

    PLACEMENT_PREVENTION = "placement_prevention"  # Magnetic Dagger
    MOVEMENT_ZONE = "movement_zone"  # Slippery Ground
    TARGET_PREVENTION = "target_prevention"  # Smoke Bomb (General)
    LOS_BLOCKER = "los_blocker"  # Physical obstacle for targeting
    AREA_STAT_MODIFIER = "area_stat_modifier"  # Aura effects
    ATTACK_IMMUNITY = "attack_immunity"  # Expert Duelist - immune to attacks except from specific attacker

    # Topology constraints (Nebkher)
    TOPOLOGY_SPLIT = (
        "topology_split"  # Tier 2: Crack in Reality - splits board into regions
    )
    TOPOLOGY_ISOLATION = (
        "topology_isolation"  # Tier 3: Shift Reality - split + isolate caster
    )


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
    )  # For prevention effects (action types)
    displacement_blocks: List[DisplacementType] = Field(
        default_factory=list
    )  # For displacement prevention (move, push, swap, place)
    except_card_colors: List[CardColor] = Field(
        default_factory=list
    )  # Exceptions to prevention (e.g. "except on Gold cards")
    except_attacker_ids: List[str] = Field(
        default_factory=list
    )  # Attackers who bypass ATTACK_IMMUNITY (e.g. "except this attacker")
    stat_type: Optional[StatType] = None  # For AREA_STAT_MODIFIER
    stat_value: int = 0  # Modifier amount
    max_value: Optional[int] = None  # For movement caps
    limit_actions_only: bool = False  # If True, only caps explicit MOVEMENT actions

    # Lifecycle
    duration: DurationType
    created_at_turn: int
    created_at_round: int

    # Activation state - set to True when source card resolves,
    # set to False when card leaves play or is turned facedown.
    # This prevents accidental re-activation and allows explicit reactivation.
    is_active: bool = False

    # Actor restriction: whose actions are blocked?
    blocks_enemy_actors: bool = True  # True = enemy actions blocked
    blocks_friendly_actors: bool = False  # True = friendly actions blocked
    blocks_self: bool = False  # True = source's own actions blocked

    # Marker linkage - if this effect was created by a marker
    marker_type: Optional[MarkerType] = None

    # Origin action type - tracks whether effect came from skill or attack
    # Used for cancelling effects by type (e.g., "cancel skill effects")
    origin_action_type: Optional[ActionType] = None

    # Topology constraint fields (for TOPOLOGY_SPLIT / TOPOLOGY_ISOLATION)
    # Used by Nebkher's Crack in Reality / Shift Reality
    split_axis: Optional[str] = (
        None  # "q", "r", or "s" - which coordinate defines the split line
    )
    split_value: int = 0  # The coordinate value of the dividing line
    isolated_hex: Optional[Hex] = (
        None  # For Tier 3 - the specific hex that is isolated (Nebkher's position)
    )
