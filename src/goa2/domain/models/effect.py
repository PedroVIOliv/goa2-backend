"""ActiveEffect model and related enums for spatial/behavioral effects."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from goa2.domain.hex import Hex
from goa2.domain.models.enums import (
    ActionType,
    CardColor,
    DisplacementType,
    MinionType,
    StatType,
)
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
    BASIC_ACTION_STAT_BONUS = (
        "basic_action_stat_bonus"  # Cordelia Broom family: one bonus to all basic stats
    )
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

    # Actor-conditional empty-hex denial (Takahide - Spinning Blade / Blade Helix)
    # Every EMPTY hex within scope.range of scope.origin_id's CURRENT position is
    # an obstacle for units on the opposing team (heroes AND minions). Occupied
    # and terrain hexes are unaffected (they are obstacles already, or handled by
    # occupancy). Consulted by is_obstacle_for_actor, so it bites on movement,
    # pushes, placement and topology range counting alike.
    EMPTY_HEX_OBSTACLE = "empty_hex_obstacle"

    # Petrify (Xargatha) - affected heroes count as terrain
    PETRIFY = "petrify"

    # Delayed trigger (carries finishing_steps, no spatial effect)
    DELAYED_TRIGGER = "delayed_trigger"

    # Illusion tokens count as friendly melee minions while the effect's
    # SOURCE hero performs actions (NebKher - Illusionary Force/Army). Gated
    # on the performer (not hardcoded NebKher): consulted via
    # rules.illusion_minion_team() by stats' minion defense modifier, unit
    # filters, and SelectStep UNIT enumeration.
    ILLUSION_MINION_EQUIVALENCE = "illusion_minion_equivalence"

    # "Next turn, after playing cards:" delayed payload (NebKher - Imbue
    # Doubt family). Fired ONLY by phases.start_resolution_phase at the
    # revelation→resolution boundary of created_at_turn + 1 (same round),
    # with the effect's source as acting player. The generic turn/round
    # expiry paths intentionally NEVER run its finishing_steps — cross-round
    # or stale copies fizzle silently.
    AFTER_CARDS_PLAYED_TRIGGER = "after_cards_played_trigger"
    # Coin bounty when an enemy minion in radius is defeated (Swift Mark for
    # Death / Hunting Season). max_value tracks remaining payouts.
    MINION_DEFEAT_BOUNTY = "minion_defeat_bounty"

    # Minion protection (Brogan Shield/Bolster/Fortify)
    MINION_PROTECTION = "minion_protection"

    # Minion battle exclusion (Wuk - Claim/Assert Dominance). Enemy minions
    # adjacent to the origin hero do not count toward the minion total during
    # minion battle. `max_value` caps how many; counts regardless of immunity.
    MINION_BATTLE_EXCLUSION = "minion_battle_exclusion"

    # Repeat prevention (Enfeeblement) - blocks action repeats
    REPEAT_PREVENTION = "repeat_prevention"

    # Global initiative inversion next turn (Emmitt - Reverse Time): heroes
    # with LOWER computed initiative act first; ties resolve as normal.
    # Checked in phases.resolve_next_action; ignores immunity (global rule).
    REVERSED_INITIATIVE = "reversed_initiative"

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

    # Discard-shield (Mrak - Stone Carapace / Rock Solid). This round, the
    # source card sits in the played/resolved area but may be discarded as if it
    # were in hand: it can absorb a forced hand-discard, and it can be used for
    # its Defense reaction. source_card_id ties the effect to the shield card.
    DISCARD_SHIELD = "discard_shield"

    # Action control (Hanu ultimate — The Ultimate Trick). While the hero at
    # scope.origin_id is the current actor resolving the card with id
    # controlled_card_id, the handler reroutes every InputRequest addressed to
    # them to source_id (Hanu). Only the decision-maker changes: actor and all
    # legality (teams, ranges, filters, stats) remain the controlled hero.
    CONTROL_NEXT_ACTION = "control_next_action"

    # Ignatia — Equilibrium: a THIS_ROUND, inert flag. Only Ignatia's own effects
    # read it (to let her choose either coin branch this round). Modeled like
    # DISCARD_SHIELD: an effect that carries no engine behavior of its own.
    EQUILIBRIUM = "equilibrium"


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
    # The hero who created the effect — its owner. Defeating them ends it. This
    # is the performer, which is not always the card's owner: NebKher's Mind Grip
    # performs a card sitting in an enemy's turn slot, and the effect is his.
    source_id: str
    source_card_id: str | None = None  # Card ID (if card-based effect)
    # Token this effect is bound to (Tali's Ice, Min's Smoke bomb, Trinkets'
    # turret aura). A token-bound effect's lifecycle is the token's and nothing
    # else's: it survives its creator's defeat, has no card to leave play, is
    # skipped by every duration sweep, and ends only when the token is removed
    # from the board.
    token_id: str | None = None
    # The unit the effect is registered against, when that is not its creator.
    # Unit-bound immunity protects its subject; Hanu's Journey is the case that
    # needs the two to differ (Hanu creates it, the displaced hero is protected).
    # Read through ``protected_unit_id``, never directly.
    subject_id: str | None = None
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
    basic_attacks_only: bool = False  # ATTACK_IMMUNITY ignores non-basic attacks when True
    non_basic_attacks_only: bool = False  # ATTACK_IMMUNITY ignores basic attacks when True
    stat_type: StatType | None = None  # For AREA_STAT_MODIFIER
    stat_value: int = 0  # Modifier amount
    apply_stat_value_only_if_result_at_least: int | None = None
    # Optional lower bound for applying stat_value. This does not clamp the
    # final stat: if the candidate result is below the bound, the modifier is
    # skipped and other effects remain untouched.
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

    # Publicly announced card color (NebKher - Imbue Doubt family). "Name a
    # color" is public information, so this is exposed in the client view for
    # all players while the effect is pending.
    named_color: CardColor | None = None

    # Static Barrier fields (Wasp)
    # When an enemy hero acts, hexes on the "opposite side" of the barrier become obstacles:
    # - Actor OUTSIDE radius -> hexes INSIDE radius are obstacles
    # - Actor INSIDE radius -> hexes OUTSIDE radius are obstacles
    barrier_radius: int = 0  # The radius boundary for the barrier
    barrier_origin_id: str | None = None  # Entity ID for radius calculation (Wasp's position)

    # Allowed discard colors for MINION_PROTECTION effects (Brogan)
    allowed_discard_colors: list[CardColor] = Field(default_factory=list)

    # MINION_PROTECTION payload. Empty means any minion type.
    protected_minion_types: list[MinionType] = Field(default_factory=list)
    sacrifice_origin_token: bool = False

    # PRE_ACTION_DISCARD: defeat the hero instead when they cannot discard
    discard_or_defeat: bool = False

    # Steps to push onto the execution stack when this effect expires
    # (for DELAYED_TRIGGER effects). Patched to List[AnyStep] in step_types.py.
    finishing_steps: list[Any] = Field(default_factory=list)

    # MOVEMENT_AURA_ZONE payload (Trailblazer): when an affected unit begins
    # a MOVEMENT action inside scope, their pathfinding call is invoked with
    # pass_through_obstacles=True.
    grants_pass_through_obstacles: bool = False

    # CONTROL_NEXT_ACTION: id of the unresolved card whose resolution is
    # controlled. Guards the remap so control fizzles if the card changes.
    controlled_card_id: str | None = None

    @property
    def protected_unit_id(self) -> str:
        """Unit this effect is registered against — its subject, else its creator.

        Unit-bound forms (immunity, minion-defeat bounty) identify their subject
        this way. Every self-targeting effect leaves ``subject_id`` unset, so the
        creator is the subject.
        """
        return self.subject_id or self.source_id
