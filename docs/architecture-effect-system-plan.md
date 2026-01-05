# GoA2 Effect System Architecture Plan

**Status:** Revised Draft v2.0
**Author:** System Architecture
**Date:** 2026-01-04
**Scope:** Comprehensive effect validation and prevention system

---

## Executive Summary

This document outlines the architectural approach for implementing a robust, scalable effect system capable of handling complex game mechanics including action prevention, movement restrictions, placement blocking, initiative manipulation, forced actions, and hand disruption.

**Key Goals:**
1. **Correctness**: Effects work consistently across all contexts (selection, execution, validation)
2. **Maintainability**: Adding new effects is straightforward and doesn't require scattered changes
3. **Frontend Support**: Provide accurate data for selection previews and UI feedback
4. **Testability**: Clear contracts enable comprehensive unit and integration testing

**Design Constraints:**
- Maximum ~10 simultaneous active effects
- Maximum ~30 board entities (units + tokens)
- Frontend requires accurate valid target previews
- Effects apply in initiative order as cards resolve

---

## 1. Current State Analysis

### What Works
- **Step-based execution system** with clear lifecycle (resolve → result → new steps)
- **Abort mechanism** (`abort_action`) for mandatory step failures
- **Filter system** for selection-time validation
- **Execution context** for passing data between steps
- **Modifier system** with duration tracking (DurationType)
- **`is_immune()` pattern** demonstrates centralized validation

### Critical Gaps
1. **No execution-layer validation** - PlaceUnitStep, SwapUnitsStep don't validate constraints
2. **No centralized validation service** - Prevention logic scattered or missing
3. **Filter-only approach** - Self-targeting effects bypass all filters
4. **Missing duration types** - No `NEXT_TURN`, `UNTIL_DEFEATED`, `UNTIL_CARD_STATE_CHANGES`
5. **No effect composition framework** - Can't combine "in radius AND enemy AND this turn"

---

## 2. Effect Stacking & Timing Rules

### 2.1 Stacking Behavior

Effects stack **additively** by default:

| Scenario | Result |
|----------|--------|
| Two `-1 Movement` modifiers | Movement reduced by 2 |
| `+2 Attack` and `-1 Attack` | Net +1 Attack |
| Multiple `PREVENT_MOVEMENT` status tags | Still prevented (boolean OR) |

### 2.2 Timing & Initiative Order

Effects apply based on **card resolution order** (initiative-driven):

```
Turn Resolution Order:
1. Hero A (Initiative 7) plays card → Effects activate immediately
2. Hero B (Initiative 5) plays card → Must respect Hero A's active effects
3. Hero C (Initiative 3) plays card → Must respect Hero A and B's effects
```

**Critical Rule:** When a card with "This Turn: X cannot Y" resolves, that restriction applies to ALL subsequent actors in the same turn, regardless of their initiative value.

### 2.3 Effect Conflict Resolution

When effects conflict (e.g., "must move" vs "cannot move"):

| Priority | Effect Type | Behavior |
|----------|-------------|----------|
| 1 (Highest) | Prevention ("cannot X") | Blocks the action entirely |
| 2 | Forced ("must X") | Requires the action if not prevented |
| 3 | Modification ("+1 to X") | Adjusts values |

**Rule:** Prevention always wins. A hero affected by "cannot move" cannot satisfy "must move 1 space".

### 2.4 Card-Based Effect Lifecycle (CRITICAL)

**Fundamental Rule:** Active effects from cards are ONLY active while their source card is in the "played" state (`hero.played_cards` or `hero.current_turn_card`).

```
Card Lifecycle:
  HAND → play_card() → UNRESOLVED (current_turn_card)
       → resolve_current_card() → RESOLVED (played_cards)
       → retrieve_cards() → HAND (effect ends!)
       → discard_card() → DISCARD (effect ends!)
```

**When Effects End:**
| Event | Effect Behavior |
|-------|-----------------|
| Card retrieved (end of round) | Effect immediately expires |
| Card discarded | Effect immediately expires |
| Card swapped out of played state | Effect immediately expires |
| Hero defeated | All hero's effects expire (cards leave board) |

**Critical Edge Case: Turn 4 "Next Turn" Effects**
```
Turn 4: Hero plays card with "Next Turn: Enemy cannot move"
        → Effect created with NEXT_TURN duration
End of Round: Cards retrieved (hero.retrieve_cards())
        → Source card moves from played_cards to hand
        → Effect immediately expires!
Turn 1 (next round): Effect was supposed to activate
        → But it's already expired because card is in hand
        → Effect NEVER triggers
```

**Implication:** "Next Turn" effects only work on Turns 1-3. A "Next Turn" effect played on Turn 4 will never activate.

### 2.5 Duration Types

```python
class DurationType(str, Enum):
    # Card-based durations (require card to be in played state)
    THIS_TURN = "THIS_TURN"           # Until end of turn OR card leaves played
    NEXT_TURN = "NEXT_TURN"           # Next turn only, IF card still played (Turn 4 = never)
    THIS_ROUND = "THIS_ROUND"         # Until end of round OR card leaves played

    # Permanent durations (NOT tied to card played state)
    PASSIVE = "PASSIVE"               # Always active - items, minion auras, Ultimates
```

**PASSIVE Duration - Special Cases:**
- **Items:** Equipped card bonuses (passive stat boosts)
- **Minion Auras:** Adjacent melee/heavy +1 defense, etc.
- **Ultimates:** Tier IV cards that are NEVER played from hand. When unlocked at Level 8, they go directly to `CardState.PASSIVE` and their effects are permanently active.

**Note:** `UNTIL_DEFEATED` and `UNTIL_CARD_RESOLVES` are NOT needed as separate types:
- Hero defeat → cards leave played state → effects expire automatically
- Card state change → effects expire automatically

---

## 3. Data Model Design

### 3.1 Model Architecture Decision

**Approach: Two-Model System**

We maintain separation between:
1. **Modifier** - Simple stat changes and status flags (existing, enhanced)
2. **ActiveEffect** - Complex spatial and behavioral effects (new)

**Rationale:**
- Modifiers are queried by `target_id` → O(N) filter is efficient
- ActiveEffects need spatial queries → different access pattern
- Backward compatibility with existing code
- Clear mental model for developers

### 3.2 Enhanced Modifier Model

```python
# src/goa2/domain/models/modifier.py (ENHANCED)

class DurationType(str, Enum):
    THIS_TURN = "THIS_TURN"
    NEXT_TURN = "NEXT_TURN"
    THIS_ROUND = "THIS_ROUND"
    PASSIVE = "PASSIVE"  # For items, minion auras, Ultimates - NOT tied to card state

class Modifier(BaseModel):
    """
    Represents a stat change or status flag on a specific target.
    Used for: +1 Attack, -2 Initiative, Venom effects, PREVENT_MOVEMENT, etc.
    """
    id: str
    source_id: str                    # Hero ID that created this
    source_card_id: Optional[str] = None  # Card ID (if card-based effect)
    target_id: BoardEntityID          # Who is affected

    # Stat modification (optional)
    stat_type: Optional[StatType] = None
    value_mod: int = 0

    # Status flag (optional) - for boolean effects
    status_tag: Optional[str] = None  # e.g., "PREVENT_MOVEMENT", "PREVENT_ATTACK"

    # Lifecycle
    duration: DurationType
    created_at_turn: int
    created_at_round: int

    class Config:
        frozen = False
```

**Card-State Tracking:**
- `source_card_id` links effect to its originating card (for debugging/tracking)
- For non-PASSIVE durations: effect is ONLY active while that card is in played state
- For PASSIVE duration: card state check is SKIPPED (always active)
- Ultimates: Can set `source_card_id` for tracking, but use `duration=PASSIVE` so they're always active

**Status Tag Convention:**
```python
# Prevention tags (checked by ValidationService)
"PREVENT_MOVEMENT"       # Cannot perform movement actions
"PREVENT_ATTACK"         # Cannot perform attack actions
"PREVENT_SKILL"          # Cannot use skill (primary) actions
"PREVENT_DEFENSE"        # Cannot use defense cards
"PREVENT_FAST_TRAVEL"    # Cannot fast travel
"PREVENT_PLACEMENT"      # Cannot be placed/teleported by enemies

# Immunity tags (checked by is_immune and filters)
"IMMUNE_TO_DAMAGE"
"IMMUNE_TO_DISPLACEMENT"

# Capability tags (positive effects)
"IGNORE_OBSTACLES"       # Can move through obstacles
```

### 3.3 New ActiveEffect Model

```python
# src/goa2/domain/models/effect.py (NEW)

class EffectType(str, Enum):
    """Categories of spatial/behavioral effects."""
    # Spatial Prevention
    PLACEMENT_PREVENTION = "placement_prevention"    # Magnetic Dagger
    MOVEMENT_ZONE = "movement_zone"                  # Slippery Ground

    # Targeting Modification
    TARGET_PREVENTION = "target_prevention"          # Smoke Bomb

    # Spatial Stat Modification
    AREA_STAT_MODIFIER = "area_stat_modifier"        # Aura effects

    # Forced Behavior
    FORCED_MOVEMENT = "forced_movement"              # Grasping Roots

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
    POINT = "point"           # Single target (specified by target_id)
    RADIUS = "radius"         # Circle around origin
    ADJACENT = "adjacent"     # Distance 1 only
    LINE = "line"             # Straight line in direction
    ZONE = "zone"             # Entire zone
    GLOBAL = "global"         # Entire board

class EffectScope(BaseModel):
    """Defines the spatial and relational scope of an effect."""
    shape: Shape
    range: int = 0                         # For RADIUS/LINE
    origin_id: Optional[str] = None        # Entity to measure from (defaults to source)
    origin_hex: Optional[Hex] = None       # Fixed location (overrides origin_id)
    affects: AffectsFilter = AffectsFilter.ALL_UNITS

    # For LINE shape
    direction: Optional[int] = None        # 0-5 for hex directions

class ActiveEffect(BaseModel):
    """
    Represents a spatial or behavioral effect that applies to an area.
    Used for: Magnetic Dagger (placement prevention in radius),
              Slippery Ground (movement restriction in area), etc.
    """
    id: str
    source_id: str                         # Hero ID that created this
    source_card_id: Optional[str] = None   # Card ID (if card-based effect)
    effect_type: EffectType

    # Spatial scope
    scope: EffectScope

    # Effect-specific payload
    restrictions: List[ActionType] = Field(default_factory=list)  # For prevention effects
    stat_type: Optional[StatType] = None   # For AREA_STAT_MODIFIER
    stat_value: int = 0                    # Modifier amount
    max_value: Optional[int] = None        # For movement caps

    # Lifecycle
    duration: DurationType
    created_at_turn: int
    created_at_round: int

    # Actor restriction: whose actions are blocked?
    blocks_enemy_actors: bool = True       # True = enemy actions blocked
    blocks_friendly_actors: bool = False   # True = friendly actions blocked
    blocks_self: bool = False              # True = source's own actions blocked
```

**Note:** Like Modifier, `source_card_id` determines if effect is card-based. If set, the effect only applies while that card remains in the hero's played state.

### 3.4 ValidationResult Model

```python
# src/goa2/engine/validation.py

class ValidationResult(BaseModel):
    """
    Standardized result for all validation checks.
    Provides data for both execution logic and frontend previews.
    """
    allowed: bool
    reason: str = ""                       # Human-readable explanation
    blocking_effect_ids: List[str] = Field(default_factory=list)
    blocking_modifier_ids: List[str] = Field(default_factory=list)

    # For frontend: additional context
    blocked_by_source: Optional[str] = None  # Hero/card that caused the block

    @staticmethod
    def allow() -> "ValidationResult":
        return ValidationResult(allowed=True)

    @staticmethod
    def deny(
        reason: str,
        effect_ids: List[str] = None,
        modifier_ids: List[str] = None,
        source: str = None
    ) -> "ValidationResult":
        return ValidationResult(
            allowed=False,
            reason=reason,
            blocking_effect_ids=effect_ids or [],
            blocking_modifier_ids=modifier_ids or [],
            blocked_by_source=source
        )
```

### 3.5 GameState Integration

```python
# src/goa2/domain/state.py (ADDITIONS)

class GameState(BaseModel):
    # ... existing fields ...

    # Effects (enhanced)
    active_modifiers: List[Modifier] = Field(default_factory=list)
    active_effects: List[ActiveEffect] = Field(default_factory=list)

    # Validation service (injected for testability)
    _validator: Optional["ValidationService"] = None

    @property
    def validator(self) -> "ValidationService":
        """Lazy-loaded validation service."""
        if self._validator is None:
            from goa2.engine.validation import ValidationService
            self._validator = ValidationService()
        return self._validator

    def set_validator(self, validator: "ValidationService"):
        """For testing: inject mock validator."""
        self._validator = validator

    # Helper methods
    def add_modifier(self, modifier: Modifier):
        """Add a stat/status modifier."""
        self.active_modifiers.append(modifier)

    def add_effect(self, effect: ActiveEffect):
        """Add a spatial/behavioral effect."""
        self.active_effects.append(effect)

    def get_modifiers_on(self, target_id: str) -> List[Modifier]:
        """Get all modifiers affecting a specific target."""
        return [m for m in self.active_modifiers if str(m.target_id) == str(target_id)]

    def get_effects_affecting(self, hex: Hex) -> List[ActiveEffect]:
        """Get all spatial effects that include this hex."""
        # Delegate to validator for spatial queries
        return self.validator.get_effects_at_location(self, hex)
```

---

## 4. Service Layer Architecture

### 4.1 ValidationService (Core)

```python
# src/goa2/engine/validation.py

from typing import List, Optional, Dict, Any
from goa2.domain.hex import Hex
from goa2.domain.models import ActionType, StatType
from goa2.domain.models.modifier import Modifier, DurationType
from goa2.domain.models.effect import ActiveEffect, EffectType, Shape, AffectsFilter

class ValidationService:
    """
    Centralized validation authority.
    Single source of truth for "can X do Y to Z?"

    Injected into GameState for testability.
    """

    # -------------------------------------------------------------------------
    # Primary Validation Methods (called by Steps and Filters)
    # -------------------------------------------------------------------------

    def can_perform_action(
        self,
        state: "GameState",
        actor_id: str,
        action_type: ActionType,
        context: Dict[str, Any] = None
    ) -> ValidationResult:
        """
        Can actor perform this action type?
        Checks: PREVENT_MOVEMENT, PREVENT_ATTACK, PREVENT_SKILL, etc.
        """
        context = context or {}

        # Map action type to status tag
        prevention_tags = {
            ActionType.MOVEMENT: "PREVENT_MOVEMENT",
            ActionType.ATTACK: "PREVENT_ATTACK",
            ActionType.SKILL: "PREVENT_SKILL",
            ActionType.DEFENSE: "PREVENT_DEFENSE",
        }

        tag = prevention_tags.get(action_type)
        if not tag:
            return ValidationResult.allow()

        # Check modifiers on actor
        for mod in state.active_modifiers:
            if str(mod.target_id) == str(actor_id) and mod.status_tag == tag:
                if self._is_modifier_active(mod, state):
                    return ValidationResult.deny(
                        reason=f"Action prevented: {action_type.value}",
                        modifier_ids=[mod.id],
                        source=mod.source_id
                    )

        return ValidationResult.allow()

    def can_move(
        self,
        state: "GameState",
        unit_id: str,
        distance: int,
        context: Dict[str, Any] = None
    ) -> ValidationResult:
        """
        Can unit move 'distance' spaces?
        Checks: PREVENT_MOVEMENT status, movement restriction effects.
        """
        context = context or {}

        # Check prevention first
        action_result = self.can_perform_action(state, unit_id, ActionType.MOVEMENT, context)
        if not action_result.allowed:
            return action_result

        # Check movement cap effects
        unit_loc = state.entity_locations.get(unit_id)
        if not unit_loc:
            return ValidationResult.deny("Unit not on board")

        max_allowed = float('inf')
        blocking_effect = None

        for effect in state.active_effects:
            if effect.effect_type != EffectType.MOVEMENT_ZONE:
                continue
            if not self._is_effect_active(effect, state):
                continue
            if not self._is_in_scope(effect, unit_id, unit_loc, state):
                continue

            if effect.max_value is not None and effect.max_value < max_allowed:
                max_allowed = effect.max_value
                blocking_effect = effect

        if distance > max_allowed:
            return ValidationResult.deny(
                reason=f"Movement limited to {max_allowed} (attempted {distance})",
                effect_ids=[blocking_effect.id] if blocking_effect else [],
                source=blocking_effect.source_id if blocking_effect else None
            )

        return ValidationResult.allow()

    def can_be_placed(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        destination: Optional[Hex] = None,
        context: Dict[str, Any] = None
    ) -> ValidationResult:
        """
        Can unit_id be placed/teleported by actor_id?
        Handles: Magnetic Dagger, Bulwark, displacement prevention.

        Args:
            unit_id: The unit being moved/placed
            actor_id: The hero performing the action
            destination: Target hex (optional, for destination-specific checks)
        """
        context = context or {}

        unit = state.get_unit(unit_id)
        actor = state.get_unit(actor_id)

        if not unit:
            return ValidationResult.deny("Unit not found")

        # Destination validation (if provided)
        if destination:
            tile = state.board.get_tile(destination)
            if not tile:
                return ValidationResult.deny("Destination not on board")
            if tile.is_occupied:
                return ValidationResult.deny("Destination occupied")

        # Check status-based prevention on the unit
        for mod in state.active_modifiers:
            if str(mod.target_id) == str(unit_id) and mod.status_tag == "PREVENT_PLACEMENT":
                if self._is_modifier_active(mod, state):
                    # Check if actor is blocked by this modifier
                    if self._actor_blocked_by_modifier(mod, actor, unit, state):
                        return ValidationResult.deny(
                            reason="Unit cannot be placed",
                            modifier_ids=[mod.id],
                            source=mod.source_id
                        )

        # Check spatial placement prevention effects
        unit_loc = state.entity_locations.get(unit_id)
        if not unit_loc:
            # Unit not on board - only check destination-based effects
            if destination:
                return self._check_destination_effects(state, destination, actor_id)
            return ValidationResult.allow()

        for effect in state.active_effects:
            if effect.effect_type != EffectType.PLACEMENT_PREVENTION:
                continue
            if not self._is_effect_active(effect, state):
                continue
            if not self._is_in_scope(effect, unit_id, unit_loc, state):
                continue

            # Check if this actor's actions are blocked
            if self._actor_blocked_by_effect(effect, actor, unit, state):
                return ValidationResult.deny(
                    reason="Placement prevented by area effect",
                    effect_ids=[effect.id],
                    source=effect.source_id
                )

        return ValidationResult.allow()

    def can_be_pushed(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        context: Dict[str, Any] = None
    ) -> ValidationResult:
        """Can unit_id be pushed by actor_id?"""
        # Reuse placement logic - push is a form of forced movement
        return self.can_be_placed(state, unit_id, actor_id, None, context)

    def can_be_swapped(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        context: Dict[str, Any] = None
    ) -> ValidationResult:
        """Can unit_id be swapped by actor_id?"""
        # Reuse placement logic - swap is a form of displacement
        return self.can_be_placed(state, unit_id, actor_id, None, context)

    def can_fast_travel(
        self,
        state: "GameState",
        unit_id: str,
        context: Dict[str, Any] = None
    ) -> ValidationResult:
        """Can unit perform fast travel?"""
        context = context or {}

        # Check status tag
        for mod in state.active_modifiers:
            if str(mod.target_id) == str(unit_id) and mod.status_tag == "PREVENT_FAST_TRAVEL":
                if self._is_modifier_active(mod, state):
                    return ValidationResult.deny(
                        reason="Fast travel prevented",
                        modifier_ids=[mod.id],
                        source=mod.source_id
                    )

        return ValidationResult.allow()

    # -------------------------------------------------------------------------
    # Query Methods (for frontend previews and debugging)
    # -------------------------------------------------------------------------

    def get_effects_at_location(
        self,
        state: "GameState",
        hex: Hex
    ) -> List[ActiveEffect]:
        """Get all active effects that include this hex in their scope."""
        result = []
        for effect in state.active_effects:
            if not self._is_effect_active(effect, state):
                continue
            # Check if hex is in effect's spatial scope
            if self._hex_in_scope(effect, hex, state):
                result.append(effect)
        return result

    def get_valid_placement_targets(
        self,
        state: "GameState",
        unit_id: str,
        actor_id: str,
        candidate_hexes: List[Hex]
    ) -> List[Hex]:
        """
        Filter candidate hexes to only those where unit can be placed.
        Used by frontend for preview highlighting.
        """
        valid = []
        for hex in candidate_hexes:
            result = self.can_be_placed(state, unit_id, actor_id, hex)
            if result.allowed:
                valid.append(hex)
        return valid

    def get_blocked_units_for_placement(
        self,
        state: "GameState",
        actor_id: str,
        candidate_unit_ids: List[str]
    ) -> Dict[str, ValidationResult]:
        """
        Check which units cannot be placed by actor.
        Returns dict mapping unit_id -> ValidationResult (with reason if blocked).
        Used by frontend for greying out invalid targets.
        """
        results = {}
        for unit_id in candidate_unit_ids:
            results[unit_id] = self.can_be_placed(state, unit_id, actor_id)
        return results

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _is_modifier_active(self, mod: Modifier, state: "GameState") -> bool:
        """
        Check if modifier is currently active.
        Order matters: (1) Check PASSIVE first, (2) Card state, (3) Duration timing.
        """
        # PASSIVE effects (items, Ultimates, minion auras) are ALWAYS active
        # Ultimates are never "played" - they go directly to PASSIVE state when unlocked
        # Skip card state check entirely for PASSIVE duration
        if mod.duration == DurationType.PASSIVE:
            return True

        # Card-based effects require source card to be in played state
        # This applies to THIS_TURN, NEXT_TURN, THIS_ROUND durations
        if mod.source_card_id:
            if not self._is_card_in_played_state(state, mod.source_id, mod.source_card_id):
                return False

        # Check temporal duration
        if mod.duration == DurationType.THIS_TURN:
            return state.turn == mod.created_at_turn and state.round == mod.created_at_round

        if mod.duration == DurationType.NEXT_TURN:
            # Active on the turn AFTER creation (within same round only!)
            # Turn 4 effects never trigger because cards are retrieved before Turn 1
            if state.round == mod.created_at_round:
                return state.turn == mod.created_at_turn + 1
            return False  # Cross-round NEXT_TURN never activates

        if mod.duration == DurationType.THIS_ROUND:
            return state.round == mod.created_at_round

        return False

    def _is_effect_active(self, effect: ActiveEffect, state: "GameState") -> bool:
        """Check if effect is currently active based on card state and duration."""
        return self._is_modifier_active(effect, state)  # Same logic

    def _is_card_in_played_state(
        self,
        state: "GameState",
        hero_id: str,
        card_id: str
    ) -> bool:
        """
        Check if a card is currently in the hero's played state.
        A card is "played" if it's in hero.played_cards OR hero.current_turn_card.
        """
        hero = state.get_hero(hero_id)
        if not hero:
            return False

        # Check current turn card (UNRESOLVED)
        if hero.current_turn_card and hero.current_turn_card.id == card_id:
            return True

        # Check played cards (RESOLVED)
        for card in hero.played_cards:
            if card.id == card_id:
                return True

        return False

    def _is_in_scope(
        self,
        effect: ActiveEffect,
        target_id: str,
        target_hex: Hex,
        state: "GameState"
    ) -> bool:
        """Check if target is within effect's spatial and relational scope."""
        scope = effect.scope

        # Check relational filter (enemy/friendly)
        if not self._matches_affects_filter(effect, target_id, state):
            return False

        # Check spatial shape
        return self._hex_in_scope(effect, target_hex, state)

    def _hex_in_scope(self, effect: ActiveEffect, hex: Hex, state: "GameState") -> bool:
        """Check if a hex is within effect's spatial scope."""
        scope = effect.scope

        if scope.shape == Shape.GLOBAL:
            return True

        origin = self._get_origin_hex(effect, state)
        if not origin:
            return False

        if scope.shape == Shape.POINT:
            return hex == origin

        if scope.shape == Shape.ADJACENT:
            return origin.distance(hex) == 1

        if scope.shape == Shape.RADIUS:
            return origin.distance(hex) <= scope.range

        if scope.shape == Shape.LINE:
            # Check if hex is on the line from origin in specified direction
            if scope.direction is None:
                return False
            return origin.is_straight_line(hex) and origin.distance(hex) <= scope.range

        if scope.shape == Shape.ZONE:
            # Check if both are in same zone
            origin_zone = self._get_zone_for_hex(origin, state)
            target_zone = self._get_zone_for_hex(hex, state)
            return origin_zone and origin_zone == target_zone

        return False

    def _get_origin_hex(self, effect: ActiveEffect, state: "GameState") -> Optional[Hex]:
        """Resolve origin point for spatial effects."""
        if effect.scope.origin_hex:
            return effect.scope.origin_hex

        origin_id = effect.scope.origin_id or effect.source_id
        return state.entity_locations.get(origin_id)

    def _get_zone_for_hex(self, hex: Hex, state: "GameState") -> Optional[str]:
        """Get zone ID containing this hex."""
        for zone_id, zone in state.board.zones.items():
            if hex in zone.hexes:
                return zone_id
        return None

    def _matches_affects_filter(
        self,
        effect: ActiveEffect,
        target_id: str,
        state: "GameState"
    ) -> bool:
        """Check if target matches the relational filter."""
        affects = effect.scope.affects

        if affects == AffectsFilter.ALL_UNITS:
            return True

        source = state.get_entity(effect.source_id)
        target = state.get_entity(target_id)

        if not source or not target:
            return False

        # Get teams
        source_team = getattr(source, 'team', None)
        target_team = getattr(target, 'team', None)

        if source_team is None or target_team is None:
            return affects == AffectsFilter.ALL_UNITS

        is_same_team = (source_team == target_team)
        is_self = (effect.source_id == target_id)

        # Check unit type
        from goa2.domain.models import Hero, Minion
        is_hero = isinstance(target, Hero)
        is_minion = isinstance(target, Minion)

        if affects == AffectsFilter.SELF:
            return is_self
        if affects == AffectsFilter.ENEMY_UNITS:
            return not is_same_team
        if affects == AffectsFilter.FRIENDLY_UNITS:
            return is_same_team and not is_self
        if affects == AffectsFilter.ENEMY_HEROES:
            return not is_same_team and is_hero
        if affects == AffectsFilter.FRIENDLY_HEROES:
            return is_same_team and not is_self and is_hero
        if affects == AffectsFilter.ALL_HEROES:
            return is_hero
        if affects == AffectsFilter.ALL_MINIONS:
            return is_minion

        return False

    def _actor_blocked_by_effect(
        self,
        effect: ActiveEffect,
        actor,
        target,
        state: "GameState"
    ) -> bool:
        """Determine if actor is blocked by this effect."""
        if not actor:
            return False

        actor_team = getattr(actor, 'team', None)
        source = state.get_entity(effect.source_id)
        source_team = getattr(source, 'team', None) if source else None

        if actor_team is None or source_team is None:
            return False

        is_actor_enemy_of_source = (actor_team != source_team)
        is_actor_self = (actor.id == effect.source_id)

        if effect.blocks_self and is_actor_self:
            return True
        if effect.blocks_enemy_actors and is_actor_enemy_of_source:
            return True
        if effect.blocks_friendly_actors and not is_actor_enemy_of_source and not is_actor_self:
            return True

        return False

    def _actor_blocked_by_modifier(
        self,
        mod: Modifier,
        actor,
        target,
        state: "GameState"
    ) -> bool:
        """Determine if actor is blocked by this modifier."""
        # For now, modifiers on a target block all enemy actions
        if not actor or not target:
            return False

        actor_team = getattr(actor, 'team', None)
        target_team = getattr(target, 'team', None)

        if actor_team is None or target_team is None:
            return False

        # Enemy trying to displace protected unit
        return actor_team != target_team

    def _check_destination_effects(
        self,
        state: "GameState",
        destination: Hex,
        actor_id: str
    ) -> ValidationResult:
        """Check if any effects prevent placement at destination."""
        # Future: Check for effects that block specific hexes
        return ValidationResult.allow()
```

### 4.2 EffectManager

```python
# src/goa2/engine/effects.py (ADDITIONS)

class EffectManager:
    """
    Manages effect lifecycle: creation, expiration, querying.
    Works alongside ValidationService.
    """

    @staticmethod
    def create_modifier(
        state: "GameState",
        source_id: str,
        target_id: str,
        stat_type: Optional[StatType] = None,
        value_mod: int = 0,
        status_tag: Optional[str] = None,
        duration: DurationType = DurationType.THIS_TURN,
        source_card_id: Optional[str] = None  # Link to source card
    ) -> Modifier:
        """Create and register a new modifier."""
        modifier = Modifier(
            id=f"mod_{state.create_entity_id('m')}",
            source_id=source_id,
            source_card_id=source_card_id,
            target_id=target_id,
            stat_type=stat_type,
            value_mod=value_mod,
            status_tag=status_tag,
            duration=duration,
            created_at_turn=state.turn,
            created_at_round=state.round
        )
        state.add_modifier(modifier)
        card_info = f" (card: {source_card_id})" if source_card_id else ""
        print(f"   [EFFECT] Created modifier: {stat_type or status_tag} on {target_id}{card_info}")
        return modifier

    @staticmethod
    def create_effect(
        state: "GameState",
        source_id: str,
        effect_type: EffectType,
        scope: EffectScope,
        duration: DurationType = DurationType.THIS_TURN,
        source_card_id: Optional[str] = None,  # Link to source card
        **kwargs
    ) -> ActiveEffect:
        """Create and register a new spatial effect."""
        effect = ActiveEffect(
            id=f"eff_{state.create_entity_id('e')}",
            source_id=source_id,
            source_card_id=source_card_id,
            effect_type=effect_type,
            scope=scope,
            duration=duration,
            created_at_turn=state.turn,
            created_at_round=state.round,
            **kwargs
        )
        state.add_effect(effect)
        card_info = f" (card: {source_card_id})" if source_card_id else ""
        print(f"   [EFFECT] Created {effect_type.value} effect from {source_id}{card_info}")
        return effect

    @staticmethod
    def expire_by_card(state: "GameState", card_id: str):
        """Remove all effects/modifiers linked to a specific card."""
        before_mods = len(state.active_modifiers)
        before_effs = len(state.active_effects)

        state.active_modifiers = [
            m for m in state.active_modifiers
            if m.source_card_id != card_id
        ]
        state.active_effects = [
            e for e in state.active_effects
            if e.source_card_id != card_id
        ]

        expired_mods = before_mods - len(state.active_modifiers)
        expired_effs = before_effs - len(state.active_effects)
        if expired_mods or expired_effs:
            print(f"   [EFFECT] Expired {expired_mods} modifiers, {expired_effs} effects from card {card_id}")

    @staticmethod
    def expire_modifiers(state: "GameState", duration: DurationType):
        """Remove all modifiers matching duration type."""
        before = len(state.active_modifiers)
        state.active_modifiers = [
            m for m in state.active_modifiers
            if m.duration != duration
        ]
        expired = before - len(state.active_modifiers)
        if expired > 0:
            print(f"   [EFFECT] Expired {expired} {duration.value} modifiers")

    @staticmethod
    def expire_effects(state: "GameState", duration: DurationType):
        """Remove all effects matching duration type."""
        before = len(state.active_effects)
        state.active_effects = [
            e for e in state.active_effects
            if e.duration != duration
        ]
        expired = before - len(state.active_effects)
        if expired > 0:
            print(f"   [EFFECT] Expired {expired} {duration.value} effects")

    @staticmethod
    def expire_by_source(state: "GameState", source_id: str):
        """Remove all effects/modifiers from a specific source (e.g., defeated hero)."""
        state.active_modifiers = [
            m for m in state.active_modifiers
            if m.source_id != source_id
        ]
        state.active_effects = [
            e for e in state.active_effects
            if e.source_id != source_id
        ]
        print(f"   [EFFECT] Expired all effects from {source_id}")

    @staticmethod
    def activate_next_turn_effects(state: "GameState"):
        """Activate NEXT_TURN effects at the start of a new turn."""
        for mod in state.active_modifiers:
            if mod.duration == DurationType.NEXT_TURN:
                if state.turn == mod.created_at_turn + 1 or (
                    mod.created_at_turn == 4 and state.turn == 1
                ):
                    mod.is_active = True

        for effect in state.active_effects:
            if effect.duration == DurationType.NEXT_TURN:
                if state.turn == effect.created_at_turn + 1 or (
                    effect.created_at_turn == 4 and state.turn == 1
                ):
                    effect.is_active = True
```

---

## 5. Integration with Existing Systems

### 5.1 Step Updates

All primitive steps must call ValidationService before executing:

```python
# PlaceUnitStep (UPDATED)
class PlaceUnitStep(GameStep):
    type: str = "place_unit"
    unit_id: Optional[str] = None
    unit_key: Optional[str] = None
    destination_key: str = "target_hex"
    target_hex_arg: Optional[Hex] = None

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve parameters
        unit_id = self.unit_id or context.get(self.unit_key) or state.current_actor_id
        dest_hex = self.target_hex_arg or context.get(self.destination_key)

        if not unit_id or not dest_hex:
            print("   [ERROR] Missing unit or destination for PlaceUnitStep")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        # Validation check
        result = state.validator.can_be_placed(
            state=state,
            unit_id=unit_id,
            actor_id=state.current_actor_id,
            destination=dest_hex,
            context=context
        )

        if not result.allowed:
            print(f"   [BLOCKED] PlaceUnitStep: {result.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        # Execute placement
        print(f"   [LOGIC] Placing {unit_id} at {dest_hex}")
        state.move_unit(unit_id, dest_hex)
        return StepResult(is_finished=True)
```

**Apply similar pattern to:**
- `SwapUnitsStep` → `validator.can_be_swapped()`
- `PushUnitStep` → `validator.can_be_pushed()`
- `MoveUnitStep` → `validator.can_move()`

### 5.2 Filter Updates

Filters become thin wrappers around ValidationService:

```python
# ForcedMovementByEnemyFilter (REFACTORED)
class CanBePlacedByActorFilter(FilterCondition):
    """
    Filters out units that cannot be placed by the current actor.
    Delegates to ValidationService for actual logic.
    """
    type: str = "can_be_placed_filter"

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False

        actor_id = state.current_actor_id
        if not actor_id:
            return True  # No actor context, allow selection

        result = state.validator.can_be_placed(
            state=state,
            unit_id=candidate,
            actor_id=actor_id,
            context=context
        )

        return result.allowed
```

### 5.3 Phase Integration

Update phases.py to handle effect expiration:

```python
# phases.py (ADDITIONS)

def end_turn(state: GameState):
    """Called at end of each turn."""
    from goa2.engine.effects import EffectManager

    # Expire THIS_TURN effects
    EffectManager.expire_modifiers(state, DurationType.THIS_TURN)
    EffectManager.expire_effects(state, DurationType.THIS_TURN)

    # Increment turn
    state.turn += 1
    if state.turn > 4:
        state.turn = 1
        end_round(state)

def start_turn(state: GameState):
    """Called at start of each turn."""
    from goa2.engine.effects import EffectManager

    # Activate NEXT_TURN effects
    EffectManager.activate_next_turn_effects(state)

def end_round(state: GameState):
    """Called at end of each round."""
    from goa2.engine.effects import EffectManager

    # Expire THIS_ROUND effects
    EffectManager.expire_modifiers(state, DurationType.THIS_ROUND)
    EffectManager.expire_effects(state, DurationType.THIS_ROUND)

    state.round += 1
```

### 5.4 Hero Card State Integration (CRITICAL)

Effects must expire when their source card leaves played state. This requires hooks in Hero methods:

```python
# src/goa2/domain/models/unit.py (ADDITIONS)

class Hero(Unit):
    # ... existing code ...

    def discard_card(self, card: Card, from_hand: bool = True):
        """Moves a card to the discard pile."""
        # ... existing discard logic ...

        # NEW: Expire effects from this card (if it was played)
        if not from_hand:  # Card was in played state
            self._expire_card_effects(card)

    def retrieve_cards(self):
        """End of Round: Return Resolved and Discarded cards to hand."""
        # Collect cards that will leave played state
        cards_leaving_played = list(self.played_cards)
        if self.current_turn_card:
            cards_leaving_played.append(self.current_turn_card)

        # ... existing retrieval logic ...

        # NEW: Expire effects from all retrieved cards
        for card in cards_leaving_played:
            self._expire_card_effects(card)

    def swap_cards(self, card_a: Card, card_b: Card):
        """Swaps two cards between their respective locations."""
        # Determine which cards are leaving played state
        was_a_played = card_a in self.played_cards or card_a == self.current_turn_card
        was_b_played = card_b in self.played_cards or card_b == self.current_turn_card

        # ... existing swap logic ...

        # NEW: Expire effects for cards that left played state
        # After swap, check if they're still in played state
        is_a_played = card_a in self.played_cards or card_a == self.current_turn_card
        is_b_played = card_b in self.played_cards or card_b == self.current_turn_card

        if was_a_played and not is_a_played:
            self._expire_card_effects(card_a)
        if was_b_played and not is_b_played:
            self._expire_card_effects(card_b)

    def _expire_card_effects(self, card: Card):
        """
        Remove all effects/modifiers that were created by this card.
        Called when card leaves played state.

        Note: This is eager expiration for cleanup. The ValidationService
        also checks card state, so effects are double-protected.
        """
        # This requires access to GameState, which Hero doesn't have directly.
        # Solution: Use a callback or event system.
        # See Section 5.5 for implementation options.
        pass
```

### 5.5 Effect Expiration Architecture

Since Hero doesn't have direct access to GameState, we need a mechanism to expire effects when cards leave played state:

**Option A: Event-Based (Recommended)**
```python
# Hero emits events, GameState/EffectManager listens

class Hero(Unit):
    on_card_left_played: Callable[[str, str], None] = None  # (hero_id, card_id)

    def _expire_card_effects(self, card: Card):
        if self.on_card_left_played:
            self.on_card_left_played(self.id, card.id)

# In GameState initialization:
def _setup_hero_callbacks(self):
    for team in self.teams.values():
        for hero in team.heroes:
            hero.on_card_left_played = lambda h, c: EffectManager.expire_by_card(self, c)
```

**Option B: Lazy Expiration Only**
```python
# Don't eagerly expire - rely on ValidationService checking card state
# Effects remain in lists but are filtered out during queries
# Cleanup happens at phase boundaries

def end_round(state: GameState):
    # Clean up stale effects (cards already in hand, so effects inactive)
    state.active_modifiers = [
        m for m in state.active_modifiers
        if state.validator._is_modifier_active(m, state) or m.duration == DurationType.PASSIVE
    ]
    state.active_effects = [
        e for e in state.active_effects
        if state.validator._is_effect_active(e, state) or e.duration == DurationType.PASSIVE
    ]
```

**Recommendation:** Use Option B (Lazy Expiration) for simplicity. The ValidationService already checks card state on every query, so effects are correctly filtered. Eager expiration is just an optimization for memory cleanup.

### 5.6 Hero Defeat Integration

When a hero is defeated, their cards implicitly leave played state. The ValidationService's `_is_card_in_played_state` check handles this automatically because:
1. Defeated hero is removed from board
2. Their `played_cards` and `current_turn_card` become inaccessible
3. ValidationService returns `False` for card state check

For explicit cleanup (optional):
```python
# In DefeatUnitStep (OPTIONAL - for memory cleanup)
def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
    # ... existing defeat logic ...

    # Clean up effects from defeated hero's cards
    from goa2.engine.effects import EffectManager
    EffectManager.expire_by_hero(state, defeated_unit_id)
```

```python
# In EffectManager
@staticmethod
def expire_by_hero(state: "GameState", hero_id: str):
    """Remove all effects/modifiers from a hero (all their cards)."""
    state.active_modifiers = [
        m for m in state.active_modifiers
        if m.source_id != hero_id
    ]
    state.active_effects = [
        e for e in state.active_effects
        if e.source_id != hero_id
    ]
    print(f"   [EFFECT] Expired all effects from hero {hero_id}")
```

---

## 6. Effect Creation Steps

### 6.1 CreateModifierStep

```python
class CreateModifierStep(GameStep):
    """Creates a Modifier in the game state."""
    type: str = "create_modifier"

    target_id: Optional[str] = None
    target_key: Optional[str] = None  # Read from context

    stat_type: Optional[StatType] = None
    value_mod: int = 0
    status_tag: Optional[str] = None
    duration: DurationType = DurationType.THIS_TURN

    # Card linkage (for card-based effects)
    source_card_id: Optional[str] = None  # Explicit card ID
    use_context_card: bool = True         # If True, use "current_card_id" from context

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        target = self.target_id or context.get(self.target_key)
        if not target:
            print("   [ERROR] No target for CreateModifierStep")
            return StepResult(is_finished=True)

        # Resolve source card ID
        card_id = self.source_card_id
        if card_id is None and self.use_context_card:
            card_id = context.get("current_card_id")

        from goa2.engine.effects import EffectManager
        EffectManager.create_modifier(
            state=state,
            source_id=state.current_actor_id,
            source_card_id=card_id,  # Link to card
            target_id=target,
            stat_type=self.stat_type,
            value_mod=self.value_mod,
            status_tag=self.status_tag,
            duration=self.duration
        )

        return StepResult(is_finished=True)
```

### 6.2 CreateEffectStep

```python
class CreateEffectStep(GameStep):
    """Creates a spatial ActiveEffect in the game state."""
    type: str = "create_effect"

    effect_type: EffectType
    scope: EffectScope
    duration: DurationType = DurationType.THIS_TURN

    restrictions: List[ActionType] = Field(default_factory=list)
    stat_type: Optional[StatType] = None
    stat_value: int = 0
    max_value: Optional[int] = None

    blocks_enemy_actors: bool = True
    blocks_friendly_actors: bool = False
    blocks_self: bool = False

    # Card linkage (for card-based effects)
    source_card_id: Optional[str] = None  # Explicit card ID
    use_context_card: bool = True         # If True, use "current_card_id" from context

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve source card ID
        card_id = self.source_card_id
        if card_id is None and self.use_context_card:
            card_id = context.get("current_card_id")

        from goa2.engine.effects import EffectManager
        EffectManager.create_effect(
            state=state,
            source_id=state.current_actor_id,
            source_card_id=card_id,  # Link to card
            effect_type=self.effect_type,
            scope=self.scope,
            duration=self.duration,
            restrictions=self.restrictions,
            stat_type=self.stat_type,
            stat_value=self.stat_value,
            max_value=self.max_value,
            blocks_enemy_actors=self.blocks_enemy_actors,
            blocks_friendly_actors=self.blocks_friendly_actors,
            blocks_self=self.blocks_self
        )

        return StepResult(is_finished=True)
```

### 6.3 Setting up current_card_id in Context

The `ResolveCardTextStep` must set `current_card_id` in context before card effects run:

```python
# In ResolveCardTextStep (UPDATED)
def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
    hero = state.get_hero(state.current_actor_id)
    card = hero.current_turn_card

    if not card:
        return StepResult(is_finished=True)

    # Set card ID in context for effect creation
    context["current_card_id"] = card.id

    # Get and execute card effect
    effect = CardEffectRegistry.get(card.effect_id)
    if effect:
        steps = effect.get_steps(state, hero, card)
        return StepResult(is_finished=True, new_steps=steps)

    return StepResult(is_finished=True)
```

---

## 7. Example Card Implementations

### 7.1 Magnetic Dagger (Placement Prevention)

```python
@register_effect("magnetic_dagger")
class MagneticDaggerEffect(CardEffect):
    """
    Card Text: "Attack. This Turn: Enemy heroes in Radius 3 cannot be
    placed or swapped by enemy actions."
    """
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        damage = card.primary_action_value or 0
        radius = card.radius_value or 3

        return [
            # 1. Standard attack
            AttackSequenceStep(damage=damage, range_val=1),

            # 2. Create placement prevention effect
            CreateEffectStep(
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=radius,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_HEROES
                ),
                duration=DurationType.THIS_TURN,
                restrictions=[ActionType.MOVEMENT],  # Covers place/swap
                blocks_enemy_actors=True,
                blocks_friendly_actors=False,
                blocks_self=False
            )
        ]
```

### 7.2 Slippery Ground (Movement Restriction)

```python
@register_effect("slippery_ground")
class SlipperyGroundEffect(CardEffect):
    """
    Card Text: "This Turn: Adjacent enemies can only move up to 1 space."
    """
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(
                    shape=Shape.ADJACENT,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_UNITS
                ),
                duration=DurationType.THIS_TURN,
                max_value=1  # Can only move 1 space
            )
        ]
```

### 7.3 Stone Gaze (Next Turn Prevention)

```python
@register_effect("stone_gaze")
class StoneGazeEffect(CardEffect):
    """
    Card Text: "Next Turn: Target enemy hero cannot move."
    """
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        return [
            # Select target
            SelectStep(
                target_type="UNIT",
                prompt="Select enemy hero to petrify",
                output_key="stone_target",
                filters=[
                    RangeFilter(max_range=card.range_value or 3),
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="HERO"),
                    ImmunityFilter()
                ]
            ),

            # Apply movement prevention
            CreateModifierStep(
                target_key="stone_target",
                status_tag="PREVENT_MOVEMENT",
                duration=DurationType.NEXT_TURN
            )
        ]
```

### 7.4 Venom (Stat Reduction)

```python
@register_effect("venom_strike")
class VenomStrikeEffect(CardEffect):
    """
    Card Text: "Attack. This Round: Target has -1 Attack, -1 Defense, -1 Initiative."
    """
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        damage = card.primary_action_value or 0

        return [
            # Attack (sets "victim_id" in context)
            AttackSequenceStep(damage=damage, range_val=1),

            # Apply venom effects (only if attack connected)
            CreateModifierStep(
                target_key="victim_id",
                stat_type=StatType.ATTACK,
                value_mod=-1,
                duration=DurationType.THIS_ROUND,
                active_if_key="victim_id"
            ),
            CreateModifierStep(
                target_key="victim_id",
                stat_type=StatType.DEFENSE,
                value_mod=-1,
                duration=DurationType.THIS_ROUND,
                active_if_key="victim_id"
            ),
            CreateModifierStep(
                target_key="victim_id",
                stat_type=StatType.INITIATIVE,
                value_mod=-1,
                duration=DurationType.THIS_ROUND,
                active_if_key="victim_id"
            )
        ]
```

### 7.5 Ultimate Card (Permanent Passive)

```python
@register_effect("tidal_mastery_ultimate")
class TidalMasteryUltimateEffect(CardEffect):
    """
    Tier IV Ultimate - Permanent Passive
    Card Text: "You have +1 Range on all attacks."

    Note: Ultimates are never "played" from hand. When unlocked at Level 8,
    they go to CardState.PASSIVE and their effects are always active.
    """
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        return [
            # PASSIVE duration = always active, ignores card state check
            # source_card_id set for tracking, but doesn't affect activation
            CreateModifierStep(
                target_id=hero.id,  # Affects self
                stat_type=StatType.RANGE,
                value_mod=1,
                duration=DurationType.PASSIVE,  # Never expires
                source_card_id=card.id,         # For tracking only
                use_context_card=False          # Don't use context, use explicit ID
            )
        ]

# Note: Ultimate effects are typically registered once when the card is unlocked,
# not on every turn. The registration happens in the Level Up logic:
#
# def unlock_ultimate(hero: Hero, ultimate_card: Card, state: GameState):
#     ultimate_card.state = CardState.PASSIVE
#     effect = CardEffectRegistry.get(ultimate_card.effect_id)
#     if effect:
#         steps = effect.get_steps(state, hero, ultimate_card)
#         # Execute steps immediately to create the passive modifiers
#         for step in steps:
#             step.resolve(state, {"current_card_id": ultimate_card.id})
```

---

## 8. Migration Strategy

### Phase 1: Foundation (Core Infrastructure)

**Goal:** Establish the validation pattern with minimal changes

**Tasks:**
1. Create new files:
   - `src/goa2/domain/models/effect.py` (ActiveEffect, EffectScope, enums)
   - `src/goa2/engine/validation.py` (ValidationService, ValidationResult)

2. Enhance existing:
   - Add `DurationType.NEXT_TURN` to modifier.py
   - Add `active_effects: List[ActiveEffect]` to GameState
   - Add `validator` property to GameState

3. Update one step as proof:
   - `PlaceUnitStep` with validation call

4. Write tests:
   - ValidationService unit tests
   - PlaceUnitStep integration tests

**Success Criteria:**
- PlaceUnitStep respects validation
- Existing tests still pass
- Can create and query effects

### Phase 2: Effect Lifecycle

**Goal:** Complete effect creation and expiration

**Tasks:**
1. Implement EffectManager fully
2. Add CreateModifierStep and CreateEffectStep
3. Integrate with phases.py (expiration calls)
4. Add DefeatUnitStep integration (expire on death)
5. Implement NEXT_TURN activation logic

**Success Criteria:**
- Effects expire correctly at turn/round boundaries
- NEXT_TURN effects activate properly
- Hero defeat clears their effects

### Phase 3: Step Migration

**Goal:** All primitive steps use validation

**Tasks:**
1. Update steps with validation:
   - SwapUnitsStep
   - PushUnitStep
   - MoveUnitStep
   - AttackSequenceStep (for action prevention)

2. Update filters to use ValidationService:
   - Refactor ForcedMovementByEnemyFilter
   - Create new CanBePlacedByActorFilter

3. Comprehensive integration tests

**Success Criteria:**
- All movement/placement steps validate
- Filters and steps share validation logic
- No regressions

### Phase 4: Effect Types Implementation

**Goal:** Implement all core effect types

**Batches:**
1. **Prevention Effects:**
   - PLACEMENT_PREVENTION (Magnetic Dagger pattern)
   - MOVEMENT_ZONE (Slippery Ground pattern)
   - Action prevention via status tags

2. **Stat Modification Effects:**
   - AREA_STAT_MODIFIER for auras
   - Integrate with existing get_computed_stat

3. **Complex Effects:**
   - TARGET_PREVENTION (Smoke Bomb)
   - FORCED_MOVEMENT (if needed)

**Success Criteria:**
- Can implement any card from the rulebook
- Effects compose correctly
- Frontend can query valid targets

### Phase 5: Testing & Polish

**Goal:** Production-ready system

**Tasks:**
1. Edge case tests:
   - Multiple overlapping effects
   - Effect stacking scenarios
   - Initiative order edge cases

2. Frontend integration:
   - Expose `get_valid_placement_targets()`
   - Expose `get_blocked_units_for_placement()`
   - Add effect information to input requests

3. Performance validation:
   - Test with 10 effects + 30 entities
   - Profile validation calls

4. Documentation:
   - Update ARCHITECTURE.md
   - Add effect implementation guide

**Success Criteria:**
- No gameplay bugs
- Frontend has all needed data
- Performance acceptable

---

## 9. Testing Strategy

### Unit Tests

```python
# tests/engine/test_validation_service.py

class TestValidationService:

    def test_can_be_placed_basic(self):
        """Unit can be placed when no effects exist."""
        state = create_test_state()
        result = state.validator.can_be_placed(
            state, "hero_1", "hero_1", Hex(5, 5)
        )
        assert result.allowed is True

    def test_placement_prevention_blocks_enemy(self):
        """Placement prevention effect blocks enemy placement."""
        state = create_test_state()
        hero = state.get_hero("blue_hero")

        # Simulate card being played (in played state)
        card = hero.hand[0]
        hero.play_card(card)
        hero.resolve_current_card()  # Card now in played_cards

        # Blue hero creates effect linked to the card
        effect = ActiveEffect(
            id="eff_1",
            source_id="blue_hero",
            source_card_id=card.id,  # Linked to card
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(
                shape=Shape.RADIUS,
                range=3,
                origin_id="blue_hero",
                affects=AffectsFilter.ENEMY_UNITS
            ),
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1,
            blocks_enemy_actors=True
        )
        state.active_effects.append(effect)

        # Place blue hero at origin
        state.entity_locations["blue_hero"] = Hex(0, 0)
        # Place red hero in radius
        state.entity_locations["red_hero"] = Hex(2, 0)

        # Red hero tries to place themselves
        state.current_actor_id = "red_hero"
        result = state.validator.can_be_placed(
            state, "red_hero", "red_hero", Hex(3, 0)
        )

        assert result.allowed is False
        assert "eff_1" in result.blocking_effect_ids

    def test_modifier_stacking(self):
        """Multiple stat modifiers stack additively."""
        state = create_test_state()

        # Add two -1 movement modifiers (no card linkage = always active)
        state.active_modifiers.append(Modifier(
            id="mod_1", source_id="card_1", target_id="hero_1",
            stat_type=StatType.MOVEMENT, value_mod=-1,
            duration=DurationType.THIS_TURN,
            created_at_turn=1, created_at_round=1
        ))
        state.active_modifiers.append(Modifier(
            id="mod_2", source_id="card_2", target_id="hero_1",
            stat_type=StatType.MOVEMENT, value_mod=-1,
            duration=DurationType.THIS_TURN,
            created_at_turn=1, created_at_round=1
        ))

        # Base movement 3, should be reduced to 1
        from goa2.engine.stats import get_computed_stat
        result = get_computed_stat(state, "hero_1", StatType.MOVEMENT, base_value=3)
        assert result == 1

    def test_initiative_order_matters(self):
        """Effect from earlier actor blocks later actor."""
        state = create_test_state()
        state.turn = 1
        state.round = 1

        # Hero A (init 7) plays "enemies cannot move"
        state.active_modifiers.append(Modifier(
            id="mod_1", source_id="hero_a", target_id="hero_b",
            status_tag="PREVENT_MOVEMENT",
            duration=DurationType.THIS_TURN,
            created_at_turn=1, created_at_round=1
        ))

        # Hero B (init 5) tries to move
        result = state.validator.can_perform_action(
            state, "hero_b", ActionType.MOVEMENT
        )

        assert result.allowed is False


class TestCardStateEffectLifecycle:
    """Tests for the critical card-state based effect lifecycle."""

    def test_effect_inactive_when_card_not_played(self):
        """Effect is inactive if source card is not in played state."""
        state = create_test_state()
        hero = state.get_hero("blue_hero")
        card = hero.hand[0]

        # Create effect linked to card that's still in HAND
        effect = ActiveEffect(
            id="eff_1",
            source_id="blue_hero",
            source_card_id=card.id,  # Card is in hand, NOT played
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL, affects=AffectsFilter.ENEMY_UNITS),
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1,
            blocks_enemy_actors=True
        )
        state.active_effects.append(effect)

        # Effect should NOT be active (card not played)
        assert state.validator._is_effect_active(effect, state) is False

    def test_effect_active_when_card_played(self):
        """Effect is active when source card is in played state."""
        state = create_test_state()
        hero = state.get_hero("blue_hero")
        card = hero.hand[0]

        # Play the card
        hero.play_card(card)
        hero.resolve_current_card()  # Now in played_cards

        # Create effect linked to played card
        effect = ActiveEffect(
            id="eff_1",
            source_id="blue_hero",
            source_card_id=card.id,
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL, affects=AffectsFilter.ENEMY_UNITS),
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1,
            blocks_enemy_actors=True
        )
        state.active_effects.append(effect)

        # Effect should be active
        assert state.validator._is_effect_active(effect, state) is True

    def test_effect_expires_on_card_retrieval(self):
        """Effect becomes inactive when source card is retrieved to hand."""
        state = create_test_state()
        hero = state.get_hero("blue_hero")
        card = hero.hand[0]

        # Play the card
        hero.play_card(card)
        hero.resolve_current_card()

        # Create effect
        effect = ActiveEffect(
            id="eff_1",
            source_id="blue_hero",
            source_card_id=card.id,
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL, affects=AffectsFilter.ENEMY_UNITS),
            duration=DurationType.THIS_ROUND,  # Would last all round normally
            created_at_turn=1,
            created_at_round=1,
            blocks_enemy_actors=True
        )
        state.active_effects.append(effect)

        # Effect is active
        assert state.validator._is_effect_active(effect, state) is True

        # Retrieve cards (end of round)
        hero.retrieve_cards()

        # Effect should now be INACTIVE (card back in hand)
        assert state.validator._is_effect_active(effect, state) is False

    def test_turn_4_next_turn_effect_never_triggers(self):
        """NEXT_TURN effect played on Turn 4 never activates (cards retrieved first)."""
        state = create_test_state()
        state.turn = 4
        state.round = 1

        hero = state.get_hero("blue_hero")
        card = hero.hand[0]

        # Play card on turn 4
        hero.play_card(card)
        hero.resolve_current_card()

        # Create NEXT_TURN effect
        effect = ActiveEffect(
            id="eff_1",
            source_id="blue_hero",
            source_card_id=card.id,
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL, affects=AffectsFilter.ENEMY_UNITS),
            duration=DurationType.NEXT_TURN,  # Should activate Turn 1 of next round
            created_at_turn=4,
            created_at_round=1,
            blocks_enemy_actors=True
        )
        state.active_effects.append(effect)

        # Effect not active on Turn 4
        assert state.validator._is_effect_active(effect, state) is False

        # Simulate end of round (cards retrieved)
        hero.retrieve_cards()
        state.turn = 1
        state.round = 2

        # Effect should STILL be inactive because card is now in hand
        assert state.validator._is_effect_active(effect, state) is False

    def test_passive_effect_not_tied_to_card(self):
        """PASSIVE effects (items, Ultimates) are not tied to card state."""
        state = create_test_state()

        # Create PASSIVE effect (no source_card_id)
        modifier = Modifier(
            id="mod_1",
            source_id="blue_hero",
            source_card_id=None,  # Not card-based
            target_id="blue_hero",
            stat_type=StatType.ATTACK,
            value_mod=1,
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1
        )
        state.active_modifiers.append(modifier)

        # Effect should be active regardless of card state
        assert state.validator._is_modifier_active(modifier, state) is True
```

### Integration Tests

```python
# tests/integration/test_effect_scenarios.py

def test_magnetic_dagger_prevents_noble_blade_nudge():
    """
    Scenario: Wasp plays Magnetic Dagger, then Arien tries Noble Blade.
    Expected: Arien cannot nudge enemies in Magnetic Dagger radius.
    """
    game = create_game_with_heroes(["wasp", "arien", "enemy"])

    # Setup positions
    place_hero(game, "wasp", Hex(0, 0))
    place_hero(game, "arien", Hex(5, 0))
    place_hero(game, "enemy", Hex(1, 0))  # In wasp's radius, adjacent to arien's target

    # Wasp plays Magnetic Dagger (creates radius 3 placement prevention)
    resolve_card(game, "wasp", "magnetic_dagger")

    # Arien tries Noble Blade
    # Selection for "nudge unit" should NOT include "enemy" (in prevention zone)
    valid_nudge_targets = get_valid_targets(game, "arien", "noble_blade_nudge")

    assert "enemy" not in valid_nudge_targets

def test_prevention_wins_over_forced():
    """
    Scenario: Hero has "cannot move" and tries to use "must move 1".
    Expected: Cannot move wins, action fails.
    """
    state = create_test_state()

    # Apply prevention
    state.active_modifiers.append(Modifier(
        id="mod_1", source_id="enemy", target_id="hero_1",
        status_tag="PREVENT_MOVEMENT",
        duration=DurationType.THIS_TURN,
        created_at_turn=1, created_at_round=1
    ))

    # Try to move
    result = state.validator.can_move(state, "hero_1", distance=1)

    assert result.allowed is False

def test_effect_expires_after_card_discarded():
    """
    Scenario: Hero plays card with effect, then card is discarded mid-turn.
    Expected: Effect immediately stops applying.
    """
    game = create_game_with_heroes(["wasp", "arien"])
    state = game.state

    # Wasp plays Magnetic Dagger
    wasp = state.get_hero("wasp")
    card = get_card_by_name(wasp, "magnetic_dagger")
    resolve_card(game, "wasp", "magnetic_dagger")

    # Verify effect is active
    assert len(state.active_effects) == 1
    assert state.validator._is_effect_active(state.active_effects[0], state) is True

    # Some other effect discards Wasp's played card
    wasp.discard_card(card, from_hand=False)

    # Effect should now be inactive (card left played state)
    assert state.validator._is_effect_active(state.active_effects[0], state) is False
```

---

## 10. File Organization

```
src/goa2/
├── domain/
│   └── models/
│       ├── modifier.py          # ENHANCED: Add DurationType.NEXT_TURN
│       ├── effect.py            # NEW: ActiveEffect, EffectScope, enums
│       └── ...
│
├── engine/
│   ├── validation.py            # NEW: ValidationService, ValidationResult
│   ├── effects.py               # ENHANCED: Add EffectManager
│   ├── steps.py                 # UPDATED: Add validation calls, CreateModifierStep, CreateEffectStep
│   ├── filters.py               # UPDATED: Refactor to use ValidationService
│   ├── phases.py                # UPDATED: Add expiration calls
│   └── ...
│
└── tests/
    ├── unit/
    │   ├── test_validation_service.py
    │   ├── test_effect_manager.py
    │   └── test_modifier_stacking.py
    └── integration/
        ├── test_effect_scenarios.py
        └── test_card_interactions.py
```

---

## 11. Success Metrics

### Correctness
- [ ] All effect stacking rules implemented correctly
- [ ] Initiative order respected for effect timing
- [ ] Prevention always beats forced movement
- [ ] All duration types expire correctly

### Maintainability
- [ ] New card effect implementation: < 30 lines of code
- [ ] Adding new effect type: < 1 hour
- [ ] No "special case" hacks in step execution

### Frontend Support
- [ ] `get_valid_placement_targets()` returns accurate results
- [ ] `get_blocked_units_for_placement()` includes block reasons
- [ ] ValidationResult provides enough data for UI feedback

### Performance
- [ ] 10 effects + 30 entities: < 10ms per validation call
- [ ] No performance regression in existing game flow

---

## 12. Open Questions (For Future)

1. **Effect Visualization:** How should the frontend display active effects on the board?
2. **Effect Dispel:** Should there be a way to remove specific effects mid-turn?
3. **Effect Immunity:** Can effects grant immunity to other effects?
4. **Triggered Effects:** Effects that activate on specific events (e.g., "when enemy enters radius")

---

**Document Version:** 2.1
**Last Updated:** 2026-01-04
**Status:** Ready for Implementation

**Key Change in v2.1:** Added critical card-state based effect lifecycle - effects only apply while their source card is in played state (hero.played_cards or hero.current_turn_card).
