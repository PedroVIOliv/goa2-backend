# Defense Effects System - Implementation Plan

## Overview

This document outlines the architecture for implementing primary DEFENSE card effects, following the same pattern as primary offense effects.

## Core Design Principle

**Symmetry between Offense and Defense:**

| Context | Primary Action | Secondary Action |
|---------|---------------|------------------|
| Playing card (your turn) | `effect.get_steps()` via `ResolveCardTextStep` | Standard primitives |
| Defending (reaction) | `effect.get_defense_steps()` via `ResolveDefenseTextStep` | Standard defense value |

## Card Action Categories

### Standard Cards

Most cards have a non-DEFENSE primary action (ATTACK, SKILL, MOVEMENT) and may have DEFENSE as a secondary action.

### Primary DEFENSE Cards

Cards where `primary_action == DEFENSE`. These cards:
- Cannot be played as an active action on your turn
- Only usable during reaction window when defending
- Trigger effect text when used to defend

### DEFENSE_SKILL Cards (Dual-Use)

A special category where the same effect text applies in **both contexts**:
- When used as a **primary SKILL action** on your turn
- When used as a **primary DEFENSE reaction** when attacked

Examples:
- **Wuk - Treetop Ride**: "Swap places with a tree token in radius. You may then place a minion..."
- **Mortimer - Awaken!**: "Place up to 4 zombie tokens" (Defense 3)
- **Razzle - Crowd Control**: "+2 Defense for each clone in radius" (Defense 1+)
- **Emmitt - Unstable Timeline**: "Place glitch tokens, enemy chooses swap"

For these cards, `get_steps()` handles both use cases - the same logic applies whether playing offensively or defending.

## Card Selection Rules

### When Playing a Card (Your Turn)

The player should **only be offered non-DEFENSE actions**:

- If `primary_action != DEFENSE` → offer as "Primary: {action}"
- For each `secondary_action` where `action != DEFENSE` → offer as "Secondary: {action}"
- DEFENSE is **never** an active choice on your turn

This requires a change to `ResolveCardStep` to filter out DEFENSE options.

**Exception - DEFENSE_SKILL cards**: If `primary_action == DEFENSE` but the card also functions as a SKILL (identifiable by effect design), it should be offered as a SKILL action. Implementation TBD - may need a card flag or effect metadata.

### When Defending (Reaction)

The player can select **any card with DEFENSE** (primary or secondary):

- Cards where `primary_action == DEFENSE` → triggers effect text
- Cards where `DEFENSE in secondary_actions` → standard defense value only

**No pre-filtering based on conditions**: Players can always select any defense card. If conditions aren't met (e.g., Min's smoke bomb not in range, Wasp's card vs melee attack), the defense simply fails. The card is still consumed. This matches how offense works - bad choices have consequences.

This is the existing behavior in `ReactionWindowStep`, but we need to track which type was used.

## Extended CardEffect Base Class

```python
class CardEffect(ABC):
    """Base class for all card effects."""
    
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        """
        Steps when used as primary action on your turn.
        
        For most cards: implements the primary ATTACK/SKILL/MOVEMENT effect.
        For DEFENSE_SKILL cards: also used when defending (same logic).
        
        Default: empty (for pure DEFENSE-only cards like Wasp's projectile blockers).
        """
        return []
    
    def get_defense_steps(
        self, state: GameState, defender: Hero, card: Card, context: Dict[str, Any]
    ) -> Optional[List[GameStep]]:
        """
        Steps when used as primary DEFENSE in reaction.
        
        Args:
            context: Contains attack information:
                - attack_is_ranged: bool
                - attacker_id: str
                - defender_id: str (same as defender.id)
        
        Returns:
            List of steps to execute.
            Return None to fall back to get_steps() (for DEFENSE_SKILL cards).
        
        Note: For DEFENSE_SKILL cards, you can return None here and the engine
        will use get_steps() instead, since the effect is the same in both contexts.
        """
        return None
    
    def get_on_block_steps(
        self, state: GameState, defender: Hero, card: Card, context: Dict[str, Any]
    ) -> List[GameStep]:
        """
        Steps to run after successful block ('if you do' effects).
        Only called if the defense succeeded (block_succeeded=True).
        
        Example: Wasp's Reflect Projectiles - "if you do, enemy hero discards"
        """
        return []
```

### Design Decisions

1. **`get_steps()` is no longer abstract** - Has default empty implementation. Pure DEFENSE cards (Wasp's projectile blockers) don't need to override it.

2. **`get_defense_steps()` returns `None` to use `get_steps()`** - For DEFENSE_SKILL cards where the same effect applies in both contexts, returning `None` tells the engine to use `get_steps()` instead. This avoids code duplication.

3. **`context` parameter only for defense methods** - Defense needs attack info (ranged, attacker, etc.). Offense doesn't need this. Keeping signatures different also makes the distinction clear and avoids breaking existing effects.

4. **Same registry and decorator** - No changes to `@register_effect()`. The registry stores `CardEffect` instances; callers decide which method to invoke.

## Attack Sequence Flow

Current flow:
```
AttackSequenceStep
  → SelectTargetStep (or use pre-selected target)
  → ReactionWindowStep
  → ResolveCombatStep
```

Proposed flow:
```
AttackSequenceStep
  → SelectTargetStep
  → ReactionWindowStep          # Stores defense_card_id, is_primary_defense
  → ResolveDefenseTextStep      # NEW: Calls effect.get_defense_steps() if primary
  → ResolveCombatStep           # Checks context flags (auto_block, etc.)
  → ResolveOnBlockEffectStep    # NEW: Calls effect.get_on_block_steps() if blocked
```

## Context Keys

| Key | Set By | Used By | Description |
|-----|--------|---------|-------------|
| `attack_is_ranged` | AttackSequenceStep | ResolveDefenseTextStep | True if attack is ranged |
| `attacker_id` | AttackSequenceStep | ResolveDefenseTextStep | ID of attacking unit |
| `defense_card_id` | ReactionWindowStep | ResolveDefenseTextStep | Card used for defense |
| `defender_id` | ReactionWindowStep | ResolveDefenseTextStep | ID of defending hero |
| `is_primary_defense` | ReactionWindowStep | ResolveDefenseTextStep | True if primary DEFENSE |
| `ignore_minion_defense` | get_defense_steps | ResolveCombatStep | Skip minion modifier calc |
| `auto_block` | get_defense_steps | ResolveCombatStep | Block succeeds regardless of values |
| `defense_invalid` | get_defense_steps | ResolveCombatStep | Defense fails (e.g., melee vs stop_projectiles) |
| `block_succeeded` | ResolveCombatStep | ResolveOnBlockEffectStep | True if attack was blocked |

## New Steps

### ResolveDefenseTextStep

```python
class ResolveDefenseTextStep(GameStep):
    """
    Resolves defense card effect text for primary DEFENSE cards.
    Analogous to ResolveCardTextStep for offense.
    """
    
    def resolve(self, state, context):
        card_id = context.get("defense_card_id")
        defender_id = context.get("defender_id")
        is_primary = context.get("is_primary_defense", False)
        
        # Only trigger effects for primary DEFENSE
        if not card_id or not is_primary:
            return StepResult(is_finished=True)
        
        defender = state.get_hero(defender_id)
        card = next((c for c in defender.hand if c.id == card_id), None)
        
        if not card or not card.effect_id:
            return StepResult(is_finished=True)
        
        effect = CardEffectRegistry.get(card.effect_id)
        if effect:
            # Try defense-specific steps first
            defense_steps = effect.get_defense_steps(state, defender, card, context)
            
            # If None, fall back to get_steps() (for DEFENSE_SKILL cards)
            if defense_steps is None:
                defense_steps = effect.get_steps(state, defender, card)
            
            if defense_steps:
                return StepResult(is_finished=True, new_steps=defense_steps)
        
        return StepResult(is_finished=True)
```

### ResolveOnBlockEffectStep

```python
class ResolveOnBlockEffectStep(GameStep):
    """
    Runs 'if you do' effects after a successful block.
    """
    
    def resolve(self, state, context):
        if not context.get("block_succeeded"):
            return StepResult(is_finished=True)
        
        card_id = context.get("defense_card_id")
        defender_id = context.get("defender_id")
        is_primary = context.get("is_primary_defense", False)
        
        if not card_id or not is_primary:
            return StepResult(is_finished=True)
        
        defender = state.get_hero(defender_id)
        card = ...  # Get card from defender or resolved pile
        
        effect = CardEffectRegistry.get(card.effect_id)
        if effect:
            on_block_steps = effect.get_on_block_steps(state, defender, card, context)
            if on_block_steps:
                return StepResult(is_finished=True, new_steps=on_block_steps)
        
        return StepResult(is_finished=True)
```

### SetContextFlagStep (Utility)

A generic utility step for setting context values:

```python
class SetContextFlagStep(GameStep):
    """Sets a flag in execution context."""
    key: str
    value: Any
    
    def resolve(self, state, context):
        context[self.key] = self.value
        return StepResult(is_finished=True)
```

## ResolveCombatStep Changes

Current behavior:
```python
mod_val = calculate_minion_defense_modifier(state, target_id)
total_defense = defense_card_val + mod_val
if total_defense >= attack_val:
    # BLOCKED
```

New behavior:
```python
# Check for defense_invalid (e.g., stop_projectiles vs melee)
if context.get("defense_invalid"):
    # Defense failed completely - treat as if they passed
    context["block_succeeded"] = False
    return StepResult(..., new_steps=[DefeatUnitStep(...)])

# Check for auto_block (e.g., successful stop_projectiles)
if context.get("auto_block"):
    context["block_succeeded"] = True
    return StepResult(is_finished=True)

# Standard combat resolution
if not context.get("ignore_minion_defense"):
    mod_val = calculate_minion_defense_modifier(state, target_id)
else:
    mod_val = 0

total_defense = defense_card_val + mod_val
if total_defense >= attack_val:
    context["block_succeeded"] = True
    # BLOCKED
else:
    context["block_succeeded"] = False
    # HIT
```

## ResolveCardStep Changes

Filter out DEFENSE from available options:

```python
# Current: offers all actions including primary DEFENSE
# New: skip DEFENSE actions entirely

options = []

# Primary action (only if not DEFENSE)
if card.primary_action != ActionType.DEFENSE:
    if is_action_available(card.primary_action):
        options.append({"type": "PRIMARY", "action": card.primary_action})

# Secondary actions (skip DEFENSE)
for action_type in card.secondary_actions:
    if action_type != ActionType.DEFENSE:
        if is_action_available(action_type):
            options.append({"type": "SECONDARY", "action": action_type})
```

## Example Effects

### aspiring_duelist (Modifier Defense)

```python
@register_effect("aspiring_duelist")
class AspiringDuelistEffect(CardEffect):
    """Ignore all minion defense modifiers."""
    
    # get_steps() not needed - uses default empty implementation
    
    def get_defense_steps(self, state, defender, card, context):
        return [SetContextFlagStep(key="ignore_minion_defense", value=True)]
```

### stop_projectiles (Conditional Block)

```python
@register_effect("stop_projectiles")
class StopProjectilesEffect(CardEffect):
    """Block a ranged attack."""
    
    def get_defense_steps(self, state, defender, card, context):
        if context.get("attack_is_ranged"):
            return [SetContextFlagStep(key="auto_block", value=True)]
        else:
            return [SetContextFlagStep(key="defense_invalid", value=True)]
```

### reflect_projectiles (Conditional + Triggered)

```python
@register_effect("reflect_projectiles")
class ReflectProjectilesEffect(CardEffect):
    """Block a ranged attack; if you do, enemy hero in range discards."""
    
    def get_defense_steps(self, state, defender, card, context):
        if context.get("attack_is_ranged"):
            return [SetContextFlagStep(key="auto_block", value=True)]
        else:
            return [SetContextFlagStep(key="defense_invalid", value=True)]
    
    def get_on_block_steps(self, state, defender, card, context):
        stats = compute_card_stats(state, defender.id, card)
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                ],
                prompt="Select enemy hero to force discard",
                output_key="discard_target",
                is_mandatory=False,
            ),
            ForceDiscardStep(target_key="discard_target", active_if_key="discard_target"),
        ]
```

### treetop_ride (DEFENSE_SKILL - Dual Use)

```python
@register_effect("treetop_ride")
class TreetopRideEffect(CardEffect):
    """
    Swap places with a tree token in radius. You may then place a minion...
    
    DEFENSE_SKILL card - same effect when used as SKILL on turn or DEFENSE when reacting.
    The defense value (4) is handled separately by the combat system.
    """
    
    def get_steps(self, state, hero, card):
        """Used both for primary SKILL action and primary DEFENSE reaction."""
        stats = compute_card_stats(state, hero.id, card)
        return [
            SelectStep(
                target_type=TargetType.TOKEN,
                filters=[
                    TokenTypeFilter(token_type="TREE"),
                    RangeFilter(max_range=stats.radius),
                ],
                prompt="Select tree token to swap with",
                output_key="tree_target",
                is_mandatory=False,  # If no tree, effect fails gracefully
            ),
            SwapWithTokenStep(
                unit_id=hero.id,
                token_key="tree_target",
                active_if_key="tree_target",
            ),
            # "You may then place a minion..."
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select hex to place minion (optional)",
                output_key="minion_placement",
                is_mandatory=False,
                active_if_key="tree_target",
                # ... additional filters
            ),
            # ... additional steps
        ]
    
    def get_defense_steps(self, state, defender, card, context):
        # Return None to use get_steps() - same effect in both contexts
        return None
```

## Implementation Order

### Phase 1: Infrastructure

1. Update `CardEffect` base class with new methods (default implementations)
2. Add `SetContextFlagStep` utility
3. Update `ReactionWindowStep` to store `defense_card_id`, `defender_id`, `is_primary_defense`
4. Update `AttackSequenceStep` to store `attack_is_ranged`, `attacker_id`
5. Create `ResolveDefenseTextStep` skeleton
6. Create `ResolveOnBlockEffectStep` skeleton
7. Insert new steps into `AttackSequenceStep` expansion

### Phase 2: Combat Resolution Changes

1. Update `ResolveCombatStep` to check `auto_block`, `defense_invalid`, `ignore_minion_defense`
2. Add `block_succeeded` to context after resolution
3. Write tests for new combat flags

### Phase 3: Filter DEFENSE from Card Selection

1. Update `ResolveCardStep` to exclude DEFENSE from options
2. Verify existing tests still pass
3. Write tests for DEFENSE exclusion

### Phase 4: Simple Effects

1. Implement `aspiring_duelist` (ignore minion defense)
2. Implement `stop_projectiles` (conditional block)
3. Write integration tests

### Phase 5: Complex Effects

1. Implement `expert_duelist` / `master_duelist` (modifier + immunity)
2. Implement `deflect_projectiles` / `reflect_projectiles` (triggered effects)
3. Implement `ForceDiscardStep` if not already present

## Abort Behavior in Defense Context

### The Problem (Now Resolved)

Initially, there was concern about what happens if a mandatory step fails during defense execution. Since the execution stack contains `FinalizeHeroTurnStep` for the **attacker**, an abort would incorrectly end the attacker's turn instead of just failing the defense.

### Resolution: Design Constraint (Option 4)

After comprehensive analysis of all 27 primary DEFENSE cards across all heroes, we determined that **no defense effects have truly mandatory steps that could fail mid-execution**:

| Pattern | Cards | Abort Risk |
|---------|-------|------------|
| Passive modifiers | Arien's duelists, Dodger's shields | None - can't fail |
| Simple/conditional blocks | Wasp's projectile cards, Tigerclaw's dodge | None - condition checked, then auto-block or invalid |
| Block + optional effects | "if able", "you may" qualifiers | None - optional steps skip gracefully |
| Forced effects on attacker | Tigerclaw's Riposte | None - attacker always exists |
| Condition-gated blocks | Min's smoke bomb swap, Snorri's runes | None - condition fails → defense_invalid, no abort |

**Conclusion**: All defense effects use `is_mandatory=False` for any steps that could potentially fail. This is a **design constraint** for future card implementations.

### Condition Checking Philosophy

Conditions are checked **during effect execution**, not during card selection:

```python
# Min's Poof! - "Swap with a Smoke bomb in range; if you do, block the attack."
def get_defense_steps(self, state, defender, card, context):
    smoke_bombs = find_smoke_bombs_in_range(state, defender)
    if not smoke_bombs:
        # No valid target - defense fails (card still consumed)
        return [SetContextFlagStep(key="defense_invalid", value=True)]
    
    return [
        SelectStep(..., is_mandatory=False),  # Select smoke bomb
        SwapUnitsStep(...),                    # Swap
        SetContextFlagStep(key="auto_block", value=True),
    ]
```

This mirrors how Wasp's `stop_projectiles` works - you can select it against a melee attack, but the defense simply fails.

## Resolved Questions

1. **Card discard on defense_invalid**: Yes, the card is discarded. Bad choices have consequences. No pre-filtering needed.

2. **defense_value for auto_block cards**: Ignored entirely. "Block a ranged attack" is absolute - no value comparison needed.

3. **Immunity effects (expert/master_duelist)**: Use the existing ActiveEffect system with `CreateEffectStep` in `get_on_block_steps`.

4. **DEFENSE_SKILL cards**: These use `get_steps()` for both offense and defense contexts. The same effect logic applies in both cases. The card's primary action determines when it can be played (SKILL on turn, DEFENSE when reacting), but the effect text is identical.

## Appendix: Complete Primary DEFENSE Card Reference

Analysis from comprehensive review of all heroes.

### Standard Primary DEFENSE Cards

| Hero | Card | Effect | Pattern |
|------|------|--------|---------|
| **Wasp** | Stop Projectiles | "Block a ranged attack." | Conditional block |
| **Wasp** | Deflect Projectiles | "Block a ranged attack; if you do, an enemy hero in range, other than the attacker, discards a card, if able." | Conditional + triggered |
| **Wasp** | Reflect Projectiles | "Block a ranged attack; if you do, an enemy hero in range discards a card, if able." | Conditional + triggered |
| **Tigerclaw** | Dodge | Simple block (no effect text) | Simple block |
| **Tigerclaw** | Sidestep | Block + "you may move 1 space" | Block + optional |
| **Tigerclaw** | Parry | Block + "attacker discards a card, if able" | Block + triggered |
| **Tigerclaw** | Evade | Block + optional move + optional retrieve | Block + multiple optional |
| **Tigerclaw** | Riposte | Block + "attacker discards a card, or is defeated" | Block + forced choice (safe - attacker exists) |
| **Snorri** | Oath of Fortitude | "Choose active rune: Block basic attack / Block ranged attack" | Condition-gated |
| **Snorri** | Oath of Perseverance | Choose rune → conditional block | Condition-gated |
| **Arien** | Aspiring Duelist | "Ignore all minion defense modifiers." (Defense 5) | Passive modifier |
| **Arien** | Expert Duelist | "Ignore all minion defense modifiers. This turn: immune to other enemy hero attacks." (Defense 6) | Modifier + immunity |
| **Arien** | Master Duelist | "Ignore all minion defense modifiers. This round: immune to other enemy hero attacks." (Defense 6) | Modifier + immunity |
| **Min** | Poof! | "Swap with a Smoke bomb in range; if you do, block the attack." | Swap-contingent block |
| **Min** | Vanish | "Swap with a Smoke bomb in range; if you do, block the attack." + additional effect | Swap-contingent block |
| **Min** | Ruse | "Swap with a Smoke bomb in range; if you do, block the attack." + additional effect | Swap-contingent block |
| **Dodger** | Shield of Decay | "+X Defense based on condition" | Passive modifier |
| **Dodger** | Vampiric Shield | "+X Defense based on condition" | Passive modifier |
| **Dodger** | Aegis | "+X Defense based on condition" | Passive modifier |
| **Bain** | Close Call | "If bounty ≥ X, block the attack" | Condition-gated |
| **Bain** | Narrow Escape | "If bounty ≥ X, block the attack" | Condition-gated |
| **Bain** | Perfect Getaway | "If bounty ≥ X, block the attack" + additional | Condition-gated |
| **Takahide** | Shameful Display | "(You are defeated.)" - Handicapped silver card | Self-defeat (special) |

### DEFENSE_SKILL Cards (Dual-Use)

These cards can be played as SKILL on your turn OR as DEFENSE when reacting. The effect text applies in both contexts.

| Hero | Card | Effect | Defense Value |
|------|------|--------|---------------|
| **Wuk** | Treetop Ride | "Swap places with a tree token in radius. You may then place a minion..." | Defense 4 |
| **Mortimer** | Awaken! | "Place up to 4 zombie tokens" | Defense 3 |
| **Razzle** | Crowd Control | "+2 Defense for each clone in radius" | Defense 1+ |
| **Emmitt** | Unstable Timeline | "Place glitch tokens, enemy chooses swap" | Defense ? |

### Effect Pattern Summary

| Pattern | Description | Abort Risk |
|---------|-------------|------------|
| **Simple block** | No effect text, just defense value | None |
| **Conditional block** | Block only if condition met (ranged attack, rune active, bounty level) | None - sets `defense_invalid` if not met |
| **Passive modifier** | Modifies combat calculation (ignore minion defense, +X defense) | None - can't fail |
| **Block + optional** | Block succeeds, then optional additional effects ("you may", "if able") | None - optional steps skip |
| **Block + triggered** | Block succeeds, then triggered effect on attacker or other target | None - attacker exists, "if able" for others |
| **Swap-contingent** | Must complete swap to block; if swap impossible, block fails | None - checked upfront, sets `defense_invalid` |
| **Modifier + immunity** | Passive modifier plus grants immunity for turn/round | None - uses ActiveEffect system |

