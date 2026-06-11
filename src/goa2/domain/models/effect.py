"""ActiveEffect model and related enums for spatial/behavioral effects."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from goa2.domain.hex import Hex
from goa2.domain.models.enums import ActionType, CardColor, DisplacementType, StatType
from goa2.domain.models.marker import MarkerType


class DurationType(StrEnum):
    THIS_TURN = "THIS_TURN"  # Expires at End of Turn
    NEXT_TURN = "NEXT_TURN"  # Activates next turn, expires at end of that turn
    THIS_ROUND = "THIS_ROUND"  # Expires at End of Round
    PASSIVE = "PASSIVE"  # Permanent (until source is removed)


class EffectType(StrEnum):
    """Categories of spatial/behavioral effects."""

    PLACEMENT_PREVENTION = "placement_prevention"  # Magnetic Dagger
    MOVEMENT_ZONE = "movement_zone"  # Slippery Ground
    TARGET_PREVENTION = "target_prevention"  # Smoke Bomb (General)
    LOS_BLOCKER = "los_blocker"  # Physical obstacle for targeting
    AREA_STAT_MODIFIER = "area_stat_modifier"  # Aura effects
    ATTACK_IMMUNITY = (
        "attack_immunity"  # Expert Duelist - immune to attacks except from specific attacker
    )

    # Topology constraints (Nebkher)
    TOPOLOGY_SPLIT = "topology_split"  # Tier 2: Crack in Reality - splits board into regions
    TOPOLOGY_ISOLATION = "topology_isolation"  # Tier 3: Shift Reality - split + isolate caster

    # Actor-conditional obstacle (Wasp)
    STATIC_BARRIER = (
        "static_barrier"  # Hexes become obstacles based on actor location relative to radius
    )

    # Petrify (Xargatha) - affected heroes count as terrain
    PETRIFY = "petrify"

    # Delayed trigger (carries finishing_steps, no spatial effect)
    DELAYED_TRIGGER = "delayed_trigger"

    # Minion protection (Brogan Shield/Bolster/Fortify)
    MINION_PROTECTION = "minion_protection"

    # Repeat prevention (Enfeeblement) - blocks action repeats
    REPEAT_PREVENTION = "repeat_prevention"

    # Full immunity to enemy actions (Death Seeker) - like heavy minion immunity but for heroes
    IMMUNITY_ENEMY_ACTIONS = "immunity_enemy_actions"

    # Enraged status (Ursafar) - marks card as active, checked by is_enraged()
    ENRAGED = "enraged"

    # Double item bonuses (Min - Inner Strength / Perfect Self)
    DOUBLE_ITEMS = "double_items"

    # Pre-primary-action movement grant (Misa - focus/discipline/mastery)
    # When scheduled with NEXT_TURN duration, grants the source hero an
    # optional movement of up to max_value spaces before their primary action
    # next turn. Consumed on use by ResolveCardStep.
    PRE_ACTION_MOVEMENT = "pre_action_movement"

    # Movement aura (Silverarrow - Trailblazer)
    # Grants friendly heroes in radius a movement-action-only aura that lets
    # them ignore obstacles while performing MOVEMENT actions. Checked at the
    # top of MoveSequenceStep (movement-action entry point) — effect-side
    # nudges via MoveUnitStep do NOT consult this aura.
    MOVEMENT_AURA_ZONE = "movement_aura_zone"

    # Pre-primary-action forced discard (Trinkets - Disruptor family)
    # Before an enemy hero in scope performs a primary action, that hero
    # discards a card (or is defeated, if discard_or_defeat is set). The
    # effect deactivates once a card is actually discarded. Checked by
    # ResolvePreActionDiscardStep, scheduled by ResolveCardStep.
    PRE_ACTION_DISCARD = "pre_action_discard"


class AffectsFilter(StrEnum):
    """Who is affected by this effect."""

    SELF = "self"
    FRIENDLY_UNITS = "friendly_units"
    FRIENDLY_HEROES = "friendly_heroes"
    SELF_AND_FRIENDLY_HEROES = "self_and_friendly_heroes"
    ENEMY_UNITS = "enemy_units"
    ENEMY_HEROES = "enemy_heroes"
    ALL_UNITS = "all_units"
    ALL_HEROES = "all_heroes"
    ALL_MINIONS = "all_minions"


class Shape(StrEnum):
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
    origin_id: str | None = None  # Entity to measure from (defaults to source)
    origin_hex: Hex | None = None  # Fixed location (overrides origin_id)
    affects: AffectsFilter = AffectsFilter.ALL_UNITS
    direction: int | None = None  # 0-5 for hex directions (LINE shape)


class ActiveEffect(BaseModel):
    """
    Represents a spatial or behavioral effect that applies to an area.
    Used for: Magnetic Dagger (placement prevention in radius),
              Slippery Ground (movement restriction in area), etc.
    """

    id: str
    source_id: str  # Hero ID that created this
    source_card_id: str | None = None  # Card ID (if card-based effect)
    effect_type: EffectType

    # Spatial scope
    scope: EffectScope

    # Effect-specific payload
    restrictions: list[ActionType] = Field(
        default_factory=list
    )  # For prevention effects (action types)
    displacement_blocks: list[DisplacementType] = Field(
        default_factory=list
    )  # For displacement prevention (move, push, swap, place)
    except_card_colors: list[CardColor] = Field(
        default_factory=list
    )  # Exceptions to prevention (e.g. "except on Gold cards")
    except_attacker_ids: list[str] = Field(
        default_factory=list
    )  # Attackers who bypass ATTACK_IMMUNITY (e.g. "except this attacker")
    stat_type: StatType | None = None  # For AREA_STAT_MODIFIER
    stat_value: int = 0  # Modifier amount
    max_value: int | None = None  # For movement caps
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
    marker_type: MarkerType | None = None

    # Origin action type - tracks whether effect came from skill or attack
    # Used for cancelling effects by type (e.g., "cancel skill effects")
    origin_action_type: ActionType | None = None

    # Topology constraint fields (for TOPOLOGY_SPLIT / TOPOLOGY_ISOLATION)
    # Used by Nebkher's Crack in Reality / Shift Reality
    split_axis: str | None = None  # "q", "r", or "s" - which coordinate defines the split line
    split_value: int = 0  # The coordinate value of the dividing line
    isolated_hex: Hex | None = (
        None  # For Tier 3 - the specific hex that is isolated (Nebkher's position)
    )

    # Static Barrier fields (Wasp)
    # When an enemy hero acts, hexes on the "opposite side" of the barrier become obstacles:
    # - Actor OUTSIDE radius -> hexes INSIDE radius are obstacles
    # - Actor INSIDE radius -> hexes OUTSIDE radius are obstacles
    barrier_radius: int = 0  # The radius boundary for the barrier
    barrier_origin_id: str | None = None  # Entity ID for radius calculation (Wasp's position)

    # Allowed discard colors for MINION_PROTECTION effects (Brogan)
    allowed_discard_colors: list[CardColor] = Field(default_factory=list)

    # PRE_ACTION_DISCARD: defeat the hero instead when they cannot discard
    discard_or_defeat: bool = False

    # Steps to push onto the execution stack when this effect expires
    # (for DELAYED_TRIGGER effects). Patched to List[AnyStep] in step_types.py.
    finishing_steps: list[Any] = Field(default_factory=list)

    # MOVEMENT_AURA_ZONE payload (Trailblazer): when an affected unit begins
    # a MOVEMENT action inside scope, their pathfinding call is invoked with
    # pass_through_obstacles=True.
    grants_pass_through_obstacles: bool = False
