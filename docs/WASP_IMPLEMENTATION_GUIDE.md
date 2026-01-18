# Wasp Implementation Guide

> Implementation guide for Wasp (The Warmaiden) card effects.
> Last updated: 2026-01-16

## Overview

Wasp is a telekinetic hero with 18 cards focusing on:
- **Telekinesis**: Placing/moving units without standard movement
- **Electricity**: Attacks that force discards
- **Defense**: Blocking ranged attacks with counter-effects
- **Push mechanics**: Pushing enemies with collision penalties

## Card Inventory

| Card | Tier | Color | Primary | Status | Complexity |
|------|------|-------|---------|--------|------------|
| Stop Projectiles | I | Green | DEFENSE | Done | Trivial |
| Magnetic Dagger | Gold | Gold | ATTACK | Done | Simple |
| Shock | I | Red | ATTACK | Done | Simple |
| Lift Up | I | Blue | SKILL | TODO | Moderate |
| Charged Boomerang | II | Red | ATTACK | Done | Trivial |
| Telekinesis | II | Green | SKILL | Done | Simple |
| Deflect Projectiles | II | Green | DEFENSE | Done | Simple |
| Kinetic Repulse | II | Blue | SKILL | TODO | Complex |
| Control Gravity | II | Blue | SKILL | TODO | Moderate |
| Electrocute | II | Red | ATTACK | Done | Simple |
| Thunder Boomerang | III | Red | ATTACK | TODO | Complex |
| Reflect Projectiles | III | Green | DEFENSE | Done | Simple |
| Mass Telekinesis | III | Green | SKILL | TODO | Moderate |
| Kinetic Blast | III | Blue | SKILL | TODO | Complex |
| Center of Mass | III | Blue | SKILL | TODO | Complex |
| Electroblast | III | Red | ATTACK | Done | Moderate |
| Static Barrier | Silver | Silver | SKILL | TODO | Complex |
| High Voltage | IV | Purple | PASSIVE | TODO | Very Complex |

---

## Implementation Phases

### Phase 1: Quick Wins (8 cards)

Cards that use mostly existing infrastructure.

#### 1.1 Charged Boomerang
```
Effect: "Target a unit in range and not in a straight line."
```

**Requirements:**
- New `NotInStraightLineFilter`

**Implementation:**
```python
@register_effect("charged_boomerang")
class ChargedBoomerangEffect(CardEffect):
    def get_steps(self, state, hero, card):
        stats = compute_card_stats(state, hero.id, card)
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                target_filters=[NotInStraightLineFilter()],
            ),
        ]
```

**Filter Logic:**
```python
class NotInStraightLineFilter(FilterCondition):
    """
    Excludes targets in a straight line from the actor.
    A hex is in a straight line if any of q, r, or s coordinates match.
    Adjacent hexes are always considered "in a straight line".
    """
    def apply(self, candidate, state, context):
        actor_id = state.current_actor_id
        actor_hex = state.entity_locations.get(actor_id)
        
        if isinstance(candidate, str):
            target_hex = state.entity_locations.get(candidate)
        else:
            target_hex = candidate
            
        if not actor_hex or not target_hex:
            return False
            
        # Adjacent = in straight line
        if actor_hex.distance(target_hex) <= 1:
            return False
            
        # Check if any coordinate matches (straight line in hex grid)
        return not (actor_hex.q == target_hex.q or 
                    actor_hex.r == target_hex.r or 
                    actor_hex.s == target_hex.s)
```

---

#### 1.2 Shock
```
Effect: "Target a unit adjacent to you. After the attack: 
An enemy hero in radius and not adjacent to you discards a card, if able."
```

**Requirements:**
- Existing `ForceDiscardStep`
- Existing `RangeFilter`, `TeamFilter`
- New composite: "in radius AND not adjacent"

**Implementation:**
```python
@register_effect("shock")
class ShockEffect(CardEffect):
    def get_steps(self, state, hero, card):
        stats = compute_card_stats(state, hero.id, card)
        return [
            # 1. Attack adjacent target
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            # 2. Select enemy hero in radius but not adjacent (optional)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero in radius to discard (optional)",
                output_key="shock_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius, min_range=2),  # Not adjacent
                ],
            ),
            # 3. Force discard
            ForceDiscardStep(victim_key="shock_victim"),
        ]
```

**Note:** `RangeFilter` needs `min_range` parameter (check if exists, add if not).

---

#### 1.3 Electrocute
```
Effect: "Target a unit adjacent to you. After the attack: 
An enemy hero in radius and not adjacent to you discards a card, if able."
```

**Implementation:** Same as Shock, just larger radius (stats-driven).

---

#### 1.4 Telekinesis
```
Effect: "Place a unit or a token in range, which is not in a straight line, 
into a space adjacent to you."
```

**Requirements:**
- `NotInStraightLineFilter` (from Charged Boomerang)
- Support for tokens in `SelectStep`

**Implementation:**
```python
@register_effect("telekinesis")
class TelekinesisEffect(CardEffect):
    def get_steps(self, state, hero, card):
        stats = compute_card_stats(state, hero.id, card)
        return [
            # 1. Select unit/token in range, not in straight line
            SelectStep(
                target_type=TargetType.UNIT,  # TODO: Add token support
                prompt="Select unit to teleport",
                output_key="telekinesis_target",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.range),
                    NotInStraightLineFilter(),
                ],
                skip_immunity_filter=True,  # Can move friendly units too
            ),
            # 2. Select destination adjacent to Wasp
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select destination adjacent to you",
                output_key="telekinesis_dest",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),  # Adjacent to Wasp
                    OccupiedFilter(is_occupied=False),
                ],
            ),
            # 3. Place unit
            PlaceUnitStep(
                unit_key="telekinesis_target",
                destination_key="telekinesis_dest",
            ),
        ]
```

---

#### 1.5 Electroblast
```
Effect: "Target a unit adjacent to you. After the attack: 
An enemy hero in radius and not adjacent to you discards a card, or is defeated."
```

**Requirements:**
- Existing `ForceDiscardOrDefeatStep`

**Implementation:**
```python
@register_effect("electroblast")
class ElectroblastEffect(CardEffect):
    def get_steps(self, state, hero, card):
        stats = compute_card_stats(state, hero.id, card)
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero in radius to discard/defeat (optional)",
                output_key="electroblast_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius, min_range=2),
                ],
            ),
            ForceDiscardOrDefeatStep(victim_key="electroblast_victim"),
        ]
```

---

#### 1.6 Reflect Projectiles
```
Effect: "Block a ranged attack; if you do, an enemy hero in range discards a card, if able."
```

**Requirements:**
- Existing `get_on_block_steps()` pattern (steps.py:1177-1222)

**Implementation:**
```python
@register_effect("reflect_projectiles")
class ReflectProjectilesEffect(CardEffect):
    def get_defense_steps(self, state, defender, card, context):
        # Same as stop_projectiles - block ranged, fail on melee
        if context.get("attack_is_ranged"):
            return [SetContextFlagStep(key="auto_block", value=True)]
        else:
            return [SetContextFlagStep(key="defense_invalid", value=True)]

    def get_on_block_steps(self, state, defender, card, context):
        """Triggered only if block succeeded."""
        stats = compute_card_stats(state, defender.id, card)
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero in range to discard",
                output_key="reflect_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                ],
            ),
            ForceDiscardStep(victim_key="reflect_victim"),
        ]
```

---

#### 1.7 Deflect Projectiles
```
Effect: "Block a ranged attack; if you do, an enemy hero in range, 
other than the attacker, discards a card, if able."
```

**Implementation:** Same as Reflect but exclude attacker:
```python
def get_on_block_steps(self, state, defender, card, context):
    stats = compute_card_stats(state, defender.id, card)
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select enemy hero in range to discard (not attacker)",
            output_key="deflect_victim",
            is_mandatory=False,
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=stats.range),
                ExcludeIdentityFilter(exclude_keys=["attacker_id"]),
            ],
        ),
        ForceDiscardStep(victim_key="deflect_victim"),
    ]
```

---

### Phase 2: Telekinetic Movement (4 cards)

Cards that move units while maintaining constant distance.

#### New Component: ConstantDistanceFilter

```python
class ConstantDistanceFilter(FilterCondition):
    """
    For destination selection: ensures the destination maintains 
    the same distance from origin as the unit's current position.
    
    Used for "move without moving closer or away" effects.
    """
    origin_id: Optional[str] = None  # Defaults to current_actor
    unit_key: str  # Context key for unit being moved
    
    def apply(self, candidate_hex, state, context):
        origin_id = self.origin_id or state.current_actor_id
        origin_hex = state.entity_locations.get(origin_id)
        
        unit_id = context.get(self.unit_key)
        unit_hex = state.entity_locations.get(unit_id)
        
        if not origin_hex or not unit_hex:
            return False
            
        current_distance = origin_hex.distance(unit_hex)
        new_distance = origin_hex.distance(candidate_hex)
        
        return new_distance == current_distance
```

---

#### 2.1 Lift Up
```
Effect: "Move a unit, or a token, in radius 1 space, 
without moving it away from you or closer to you. May repeat once on the same target."
```

**Implementation:**
```python
@register_effect("lift_up")
class LiftUpEffect(CardEffect):
    def get_steps(self, state, hero, card):
        stats = compute_card_stats(state, hero.id, card)
        
        move_steps = [
            # Select unit in radius
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select unit to move",
                output_key="lift_target",
                is_mandatory=True,
                filters=[RangeFilter(max_range=stats.radius)],
                skip_immunity_filter=True,
            ),
            # Select destination (1 space, same distance from Wasp)
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select destination (1 space, same distance from you)",
                output_key="lift_dest",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1, origin_key="lift_target"),
                    OccupiedFilter(is_occupied=False),
                    ConstantDistanceFilter(unit_key="lift_target"),
                ],
            ),
            PlaceUnitStep(unit_key="lift_target", destination_key="lift_dest"),
        ]
        
        return move_steps + [
            MayRepeatOnceStep(
                steps_template=move_steps,
                prompt="Repeat Lift Up on same target?",
                # Same target constraint handled by re-using lift_target
            ),
        ]
```

---

#### 2.2 Control Gravity
```
Effect: Same as Lift Up with larger radius.
```

**Implementation:** Identical to Lift Up (stats-driven radius).

---

#### 2.3 Center of Mass
```
Effect: "Move a unit, or a token, in radius 1 space, 
without moving it away from you or closer to you. 
May repeat up to two times on the same target."
```

**Requirements:**
- New `MayRepeatNTimesStep`

**New Component:**
```python
class MayRepeatNTimesStep(GameStep):
    """
    Allows repeating a sequence of steps up to N times.
    Each repeat is optional (player can decline).
    """
    steps_template: List[GameStep]
    max_repeats: int = 2
    prompt: str = "Repeat?"
    
    # Internal state
    repeats_done: int = 0
    
    def resolve(self, state, context):
        if self.repeats_done >= self.max_repeats:
            return StepResult(is_finished=True)
            
        if self.pending_input:
            if self.pending_input.get("choice") == "YES":
                self.repeats_done += 1
                # Deep copy template and spawn
                new_steps = [copy.deepcopy(s) for s in self.steps_template]
                return StepResult(
                    is_finished=False,  # Stay on stack
                    new_steps=new_steps,
                )
            else:
                return StepResult(is_finished=True)
        
        return StepResult(
            requires_input=True,
            input_request={
                "type": "CONFIRM_REPEAT",
                "prompt": f"{self.prompt} ({self.repeats_done}/{self.max_repeats} done)",
                "options": ["YES", "NO"],
            },
        )
```

---

#### 2.4 Mass Telekinesis
```
Effect: "Place a unit or a token in range, which is not in a straight line, 
into a space adjacent to you. May repeat once."
```

**Implementation:**
```python
@register_effect("mass_telekinesis")
class MassTelekinesisEffect(CardEffect):
    def get_steps(self, state, hero, card):
        stats = compute_card_stats(state, hero.id, card)
        
        teleport_steps = [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select unit to teleport",
                output_key="mass_tk_target",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=stats.range),
                    NotInStraightLineFilter(),
                ],
                skip_immunity_filter=True,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select destination adjacent to you",
                output_key="mass_tk_dest",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),
                    OccupiedFilter(is_occupied=False),
                ],
            ),
            PlaceUnitStep(unit_key="mass_tk_target", destination_key="mass_tk_dest"),
        ]
        
        return teleport_steps + [
            MayRepeatOnceStep(steps_template=teleport_steps),
        ]
```

---

### Phase 3: Push Mechanics (2 cards)

Cards that push multiple units with collision penalties.

#### New Component: MultiSelectStep

```python
class MultiSelectStep(GameStep):
    """
    Allows selecting up to N units.
    Stores results as a list in context.
    """
    target_type: TargetType
    prompt: str
    output_key: str
    max_selections: int
    filters: List[FilterCondition] = Field(default_factory=list)
    
    # Internal
    selections: List[str] = Field(default_factory=list)
```

#### New Component: PushWithCollisionStep

```python
class PushWithCollisionStep(GameStep):
    """
    Pushes a unit and triggers callback if stopped by obstacle.
    """
    target_key: str
    distance: int
    on_collision_steps: List[GameStep] = Field(default_factory=list)
    
    def resolve(self, state, context):
        target_id = context.get(self.target_key)
        # ... push logic ...
        
        if was_stopped_by_obstacle:
            context["collision_victim"] = target_id
            return StepResult(
                is_finished=True,
                new_steps=self.on_collision_steps,
            )
        
        return StepResult(is_finished=True)
```

---

#### 3.1 Kinetic Repulse
```
Effect: "Push up to 2 enemy units adjacent to you 3 spaces; 
if a pushed hero is stopped by an obstacle, that hero discards a card, if able."
```

**Implementation:**
```python
@register_effect("kinetic_repulse")
class KineticRepulseEffect(CardEffect):
    def get_steps(self, state, hero, card):
        return [
            # Select up to 2 adjacent enemies
            MultiSelectStep(
                target_type=TargetType.UNIT,
                prompt="Select up to 2 adjacent enemies to push",
                output_key="push_targets",
                max_selections=2,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            # Push each with collision check
            ForEachStep(
                list_key="push_targets",
                item_key="current_push_target",
                steps_template=[
                    PushWithCollisionStep(
                        target_key="current_push_target",
                        distance=3,
                        on_collision_steps=[
                            # Only heroes discard
                            CheckUnitTypeStep(
                                unit_key="collision_victim",
                                expected_type="HERO",
                                output_key="is_hero_collision",
                            ),
                            ForceDiscardStep(
                                victim_key="collision_victim",
                                active_if_key="is_hero_collision",
                            ),
                        ],
                    ),
                ],
            ),
        ]
```

---

#### 3.2 Kinetic Blast
```
Effect: "Push up to 2 enemy units adjacent to you 3 or 4 spaces; 
if a pushed hero is stopped by an obstacle, that hero discards a card, if able."
```

**Implementation:** Same as Kinetic Repulse but with distance choice:
```python
# Add before push:
SelectStep(
    target_type=TargetType.NUMBER,
    prompt="Choose push distance",
    output_key="push_distance",
    number_options=[3, 4],
),
```

---

### Phase 4: Conditional Repeat (1 card)

#### 4.1 Thunder Boomerang
```
Effect: "Target a unit in range and not in a straight line. 
After the attack: If you targeted a hero, may repeat once on a different target."
```

**Requirements:**
- Check if target was a hero
- Conditional `MayRepeatOnceStep`

**Implementation:**
```python
@register_effect("thunder_boomerang")
class ThunderBoomerangEffect(CardEffect):
    def get_steps(self, state, hero, card):
        stats = compute_card_stats(state, hero.id, card)
        
        return [
            # First attack
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                target_filters=[NotInStraightLineFilter()],
                store_target_key="thunder_target_1",
            ),
            # Check if hero
            CheckUnitTypeStep(
                unit_key="thunder_target_1",
                expected_type="HERO",
                output_key="can_repeat_thunder",
            ),
            # Conditional repeat
            MayRepeatOnceStep(
                active_if_key="can_repeat_thunder",
                steps_template=[
                    AttackSequenceStep(
                        damage=stats.primary_value,
                        range_val=stats.range,
                        target_filters=[
                            NotInStraightLineFilter(),
                            ExcludeIdentityFilter(exclude_keys=["thunder_target_1"]),
                        ],
                    ),
                ],
            ),
        ]
```

---

### Phase 5: Complex Effects (2 cards)

#### 5.1 Static Barrier
```
Effect: "This turn: While an enemy hero outside of radius is performing an action, 
spaces in radius count as obstacles. While an enemy hero in radius is performing an action, 
spaces outside of radius count as obstacles."
```

**Key Insight:** This is a **GLOBAL** effect that applies to ALL enemy heroes. The radius 
defines the **bubble geometry** for obstacle calculations, not who is affected.

```
┌─────────────────────────────────────────────────────────┐
│  Enemy A (outside bubble)                               │
│      │ tries to path through bubble                     │
│      ▼                                                  │
│  Hexes INSIDE radius = obstacles for this actor         │
│                                                         │
│              ┌───────────┐                              │
│              │ radius=2  │                              │
│              │   ┌───┐   │                              │
│              │   │ W │   │  ← Wasp (bubble follows her) │
│              │   └───┘   │                              │
│              │  Enemy B  │                              │
│              └───────────┘                              │
│                    │ tries to path out                  │
│                    ▼                                    │
│  Hexes OUTSIDE radius = obstacles for this actor        │
└─────────────────────────────────────────────────────────┘
```

**Requirements:**
- New `EffectType.DYNAMIC_OBSTACLE`
- New method in `ValidationService` to check dynamic obstacles
- Wire into pathfinding (pass actor context)

**Implementation:**

```python
@register_effect("static_barrier")
class StaticBarrierEffect(CardEffect):
    """
    Creates a dynamic obstacle bubble centered on Wasp.
    The bubble follows Wasp if she is moved.
    """
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        stats = compute_card_stats(state, hero.id, card)
        
        return [
            CreateEffectStep(
                effect_type=EffectType.DYNAMIC_OBSTACLE,
                scope=EffectScope(
                    shape=Shape.GLOBAL,           # Affects ALL enemy heroes
                    range=stats.radius or 2,      # Bubble boundary geometry
                    origin_id=hero.id,            # Bubble follows Wasp dynamically
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
            ),
        ]
```

**New EffectType:**
```python
# src/goa2/domain/models/effect.py
class EffectType(str, Enum):
    # ... existing ...
    DYNAMIC_OBSTACLE = "dynamic_obstacle"  # Static Barrier
```

**Validation Logic:**
```python
# src/goa2/engine/validation.py
class ValidationService:
    
    def is_dynamic_obstacle(self, state: GameState, hex: Hex, actor_id: str) -> bool:
        """
        Check if a hex counts as an obstacle for a specific actor
        due to DYNAMIC_OBSTACLE effects (Static Barrier).
        
        The bubble is centered on origin_id's CURRENT position (dynamic).
        """
        actor_hex = state.entity_locations.get(actor_id)
        if not actor_hex:
            return False
        
        for effect in state.active_effects:
            if effect.effect_type != EffectType.DYNAMIC_OBSTACLE:
                continue
            if not effect.is_active:
                continue
            if not self._is_in_scope(state, effect, actor_id):
                continue
            
            # Get CURRENT position of origin (bubble follows Wasp)
            origin_hex = state.entity_locations.get(effect.scope.origin_id)
            radius = effect.scope.range
            
            if not origin_hex:
                continue
            
            # Calculate distances
            actor_distance = origin_hex.distance(actor_hex)
            target_distance = origin_hex.distance(hex)
            
            actor_inside = actor_distance <= radius
            target_inside = target_distance <= radius
            
            # Crossing the boundary = obstacle
            # - Actor outside, target inside → blocked
            # - Actor inside, target outside → blocked
            if actor_inside != target_inside:
                return True
        
        return False
```

**Note on `_is_in_scope`:** This method already exists in `ValidationService` (line 420). 
It calls `_matches_affects_filter()` for relational checks and `_hex_in_scope()` for spatial checks.

**Important:** Currently `_hex_in_scope()` returns `True` for `Shape.GLOBAL` without checking 
board connectivity. Per Nebkher's design (see `docs/heroes/nebkher.md`), GLOBAL must verify 
that source and target are in the same connected component:

```python
# src/goa2/engine/validation.py - _hex_in_scope() needs this fix:

def _hex_in_scope(self, effect: ActiveEffect, hex: "Hex", state: "GameState") -> bool:
    """Check if a hex is within effect's spatial scope."""
    scope = effect.scope
    
    if scope.shape == Shape.GLOBAL:
        # GLOBAL means "everywhere reachable by the source" - not the entire map
        # This respects Nebkher's reality splits
        origin = self._get_origin_hex(effect, state)
        if not origin:
            return True  # No origin = truly global (rare)
        return state.board.are_connected(origin, hex)
    
    # ... rest of existing logic ...
```

This ensures Static Barrier (and all GLOBAL effects) respect Nebkher's reality splits - 
if an enemy hero is in a different "reality", the effect won't apply to them.

**Pathfinding Integration:**
```python
# src/goa2/engine/rules.py
def validate_movement_path(
    board: Board,
    start: Hex,
    end: Hex,
    max_steps: int,
    state: Optional[GameState] = None,  # NEW
    actor_id: Optional[str] = None,      # NEW
) -> bool:
    """BFS pathfinding that respects dynamic obstacles."""
    # ... existing BFS setup ...
    
    for neighbor in current.neighbors():
        # Check static obstacles
        if is_static_obstacle(board, neighbor):
            continue
        
        # Check dynamic obstacles (NEW)
        if state and actor_id:
            if state.validator.is_dynamic_obstacle(state, neighbor, actor_id):
                continue
        
        # ... rest of BFS ...
```

**Filter Update:**
```python
# src/goa2/engine/filters.py
class MovementPathFilter(FilterCondition):
    """BFS filter for movement destinations."""
    
    def apply(self, candidate: Hex, state: GameState, context: Dict[str, Any]) -> bool:
        actor_id = self.unit_id or state.current_actor_id
        start = state.entity_locations.get(actor_id)
        
        if not start:
            return False
        
        # Pass actor context for dynamic obstacle checking
        return rules.validate_movement_path(
            board=state.board,
            start=start,
            end=candidate,
            max_steps=self.range_val,
            state=state,        # NEW
            actor_id=actor_id,  # NEW
        )
```

**Why This Design:**
- Uses existing `CreateEffectStep` - no new step needed
- `Shape.GLOBAL` already exists in the enum
- `origin_id` is looked up dynamically each time (bubble follows Wasp)
- No need for `origin_hex` freezing - bubble moves with caster
- Clean separation: effect definition vs validation logic

**Estimated LOC:** ~80 (mostly validation logic)

---

#### 5.2 High Voltage (Ultimate)
```
Effect: "Each time after you perform a basic skill, you may defeat an enemy minion in radius; 
an enemy hero who was adjacent to that minion discards a card, if able."
```

**Requirements:**
- New `PassiveTrigger.AFTER_SKILL`
- Passive must track "basic skill" (non-ultimate)
- Two-step effect: defeat minion, then check adjacency for discard

**Implementation:**
```python
@register_effect("high_voltage")
class HighVoltageEffect(CardEffect):
    def get_passive_config(self):
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_SKILL,
            uses_per_turn=0,  # Unlimited
            is_optional=True,
            prompt="High Voltage: Defeat an enemy minion in radius?",
        )
    
    def get_passive_steps(self, state, hero, card, trigger, context):
        stats = compute_card_stats(state, hero.id, card)
        
        return [
            # Select minion to defeat
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy minion in radius to defeat",
                output_key="hv_minion",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius),
                ],
            ),
            # Store adjacent heroes before defeat
            FindAdjacentHeroesStep(
                unit_key="hv_minion",
                output_key="adjacent_heroes",
                team_filter="ENEMY",
            ),
            # Defeat minion
            DefeatUnitStep(victim_key="hv_minion", active_if_key="hv_minion"),
            # Force discard on adjacent heroes
            ForEachStep(
                list_key="adjacent_heroes",
                item_key="hv_discard_victim",
                steps_template=[
                    ForceDiscardStep(victim_key="hv_discard_victim"),
                ],
            ),
        ]
```

**Estimated LOC:** 100+

---

## New Components Summary

### Filters

| Filter | Purpose | Used By |
|--------|---------|---------|
| `NotInStraightLineFilter` | Exclude straight-line targets | Charged Boomerang, Telekinesis, Mass Telekinesis, Thunder Boomerang |
| `ConstantDistanceFilter` | Maintain distance from origin | Lift Up, Control Gravity, Center of Mass |

### Steps

| Step | Purpose | Used By |
|------|---------|---------|
| `MayRepeatNTimesStep` | Repeat up to N times | Center of Mass |
| `MultiSelectStep` | Select up to N targets | Kinetic Repulse, Kinetic Blast |
| `PushWithCollisionStep` | Push with obstacle callback | Kinetic Repulse, Kinetic Blast |
| `ForEachStep` | Iterate over list in context | Kinetic Repulse, Kinetic Blast, High Voltage |
| `CheckUnitTypeStep` | Check if unit is hero/minion | Thunder Boomerang, Kinetic Repulse |
| `FindAdjacentHeroesStep` | Get heroes adjacent to unit | High Voltage |

### Effect Types

| Type | Purpose | Used By |
|------|---------|---------|
| `DYNAMIC_OBSTACLE` | Actor-position-dependent obstacle zones (bubble follows caster) | Static Barrier |

### Passive Triggers

| Trigger | Purpose | Used By |
|---------|---------|---------|
| `AFTER_SKILL` | Fire after skill resolution | High Voltage |

---

## Testing Strategy

### Unit Tests Per Card

Each card effect should have tests for:
1. **Happy path** - Effect resolves correctly
2. **No valid targets** - Graceful handling
3. **Edge cases** - Boundary conditions

### Example Test Structure

```python
# tests/engine/test_wasp_effects.py

class TestChargedBoomerang:
    def test_cannot_target_straight_line(self, wasp_state):
        """Targets in straight line are excluded."""
        # Place enemy in straight line from Wasp
        # Attempt attack
        # Assert enemy not in valid targets
        
    def test_can_target_diagonal(self, wasp_state):
        """Targets not in straight line are valid."""
        # Place enemy diagonally
        # Complete attack
        # Assert damage applied

class TestShock:
    def test_discard_on_non_adjacent_hero(self, wasp_state):
        """Hero in radius but not adjacent must discard."""
        
    def test_no_discard_if_no_cards(self, wasp_state):
        """Hero with empty hand is safe."""

class TestKineticRepulse:
    def test_collision_triggers_discard(self, wasp_state):
        """Hero stopped by obstacle discards."""
        
    def test_minion_collision_no_discard(self, wasp_state):
        """Minion stopped by obstacle does not discard."""

class TestStaticBarrier:
    def test_enemy_outside_cannot_path_into_bubble(self, wasp_state):
        """Enemy outside radius cannot move to hexes inside radius."""
        
    def test_enemy_outside_cannot_path_through_bubble(self, wasp_state):
        """Enemy outside radius cannot path through the bubble."""
        
    def test_enemy_inside_cannot_path_out_of_bubble(self, wasp_state):
        """Enemy inside radius cannot move to hexes outside radius."""
        
    def test_enemy_inside_can_move_within_bubble(self, wasp_state):
        """Enemy inside radius CAN move to other hexes inside radius."""
        
    def test_enemy_outside_can_move_outside_bubble(self, wasp_state):
        """Enemy outside radius CAN move to other hexes outside radius."""
        
    def test_friendly_hero_not_affected(self, wasp_state):
        """Friendly heroes ignore the barrier entirely."""
        
    def test_caster_not_affected(self, wasp_state):
        """Wasp herself ignores the barrier."""
        
    def test_bubble_follows_wasp_when_moved(self, wasp_state):
        """If Wasp is pushed/placed, bubble center moves with her."""
        
    def test_effect_expires_end_of_turn(self, wasp_state):
        """Barrier disappears when turn ends."""
```

---

## Implementation Checklist

- [ ] **Phase 1: Quick Wins**
  - [ ] Add `NotInStraightLineFilter` to filters.py
  - [ ] Add `min_range` to `RangeFilter` (if missing)
  - [ ] Implement `charged_boomerang`
  - [ ] Implement `shock`
  - [ ] Implement `electrocute`
  - [ ] Implement `telekinesis`
  - [ ] Implement `electroblast`
  - [ ] Implement `reflect_projectiles`
  - [ ] Implement `deflect_projectiles`

- [ ] **Phase 2: Telekinetic Movement**
  - [ ] Add `ConstantDistanceFilter` to filters.py
  - [ ] Implement `lift_up`
  - [ ] Implement `control_gravity`
  - [ ] Add `MayRepeatNTimesStep` to steps.py
  - [ ] Implement `center_of_mass`
  - [ ] Implement `mass_telekinesis`

- [ ] **Phase 3: Push Mechanics**
  - [ ] Add `MultiSelectStep` to steps.py
  - [ ] Add `PushWithCollisionStep` to steps.py
  - [ ] Add `ForEachStep` to steps.py
  - [ ] Implement `kinetic_repulse`
  - [ ] Implement `kinetic_blast`

- [ ] **Phase 4: Conditional Repeat**
  - [ ] Add `CheckUnitTypeStep` to steps.py
  - [ ] Modify `AttackSequenceStep` to optionally store target
  - [ ] Implement `thunder_boomerang`

- [ ] **Phase 5: Complex Effects**
  - [ ] Add `DYNAMIC_OBSTACLE` to `EffectType` enum
  - [ ] Add `is_dynamic_obstacle()` method to `ValidationService`
  - [ ] Fix `_hex_in_scope()` to check board connectivity for `Shape.GLOBAL`
  - [ ] Update `rules.validate_movement_path()` to accept state/actor_id params
  - [ ] Update `MovementPathFilter` to pass actor context
  - [ ] Implement `static_barrier`
  - [ ] Add `AFTER_SKILL` passive trigger
  - [ ] Add `FindAdjacentHeroesStep`
  - [ ] Implement `high_voltage`

---

## References

- [CODEBASE_MAP.md](./CODEBASE_MAP.md) - Architecture overview
- [src/goa2/scripts/arien_effects.py](../src/goa2/scripts/arien_effects.py) - Reference implementations
- [src/goa2/engine/steps.py](../src/goa2/engine/steps.py) - Step patterns
- [src/goa2/engine/filters.py](../src/goa2/engine/filters.py) - Filter patterns
