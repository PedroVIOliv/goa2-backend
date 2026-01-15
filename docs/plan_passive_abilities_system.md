# Passive Abilities System - Implementation Plan

## Overview

This document outlines the architecture for implementing **passive abilities** - persistent effects that trigger during specific game events. The primary use case is **Living Tsunami** (Arien's Ultimate), but the system is designed to be extensible for future passive abilities.

## Key Concepts

### What is a Passive Ability?

A passive ability is an effect that:
- **Triggers automatically** at specific game events (e.g., before attacking)
- **Persists across turns** while its source is active
- **May have usage limits** (e.g., "once per turn")
- **May be optional** ("you may") requiring player confirmation

### Passive vs Active Card Effects

| Aspect | Active Effect | Passive Effect |
|--------|---------------|----------------|
| **Trigger** | When card is played as action | During specific game events |
| **Duration** | One-time on play | Persistent while source active |
| **Method** | `get_steps()` | `get_passive_steps()` |
| **Usage** | Once per play | Repeatable per trigger (with limits) |

## Ultimate Cards (Purple/Tier IV)

### Special Rules for Ultimates

Ultimate cards (Purple, Tier IV) have **unique lifecycle rules** that differ from regular cards:

| Aspect | Regular Cards | Ultimate Cards |
|--------|---------------|----------------|
| **Location** | Hand → Played → Discard → Deck | Never in any pile |
| **Activation** | Must be played, then RESOLVED | Always active at Level 8+ |
| **State tracking** | Uses `CardState` enum | Uses hero level check |
| **Face-up/down** | Can be turned facedown | N/A - always "active" |

### How Ultimates Work

1. **Not in normal card flow**: Ultimates are never in `hand`, `played_cards`, `discard_pile`, or `deck`
2. **Level-gated**: Active only when hero reaches Level 8
3. **Always available**: Once unlocked, the passive is always active (no RESOLVED check needed)
4. **Stored separately**: Should be accessed via `hero.ultimate` or similar field

### Implementation for Ultimate Detection

When checking for passive abilities, the system must:
1. Check regular `played_cards` (RESOLVED + face-up) for standard passives
2. Check `hero.level >= 8` for ultimate passives
3. Ultimate cards skip the CardState/face-up validation entirely

```python
# Pseudo-code for passive detection
def get_active_passive_sources(hero: Hero) -> List[Card]:
    sources = []
    
    # Regular cards: must be RESOLVED and face-up
    for card in hero.played_cards:
        if card.state == CardState.RESOLVED and not card.is_facedown:
            if has_passive(card):
                sources.append(card)
    
    # Ultimate: active if level 8+
    if hero.level >= 8 and hero.ultimate_card:
        if has_passive(hero.ultimate_card):
            sources.append(hero.ultimate_card)
    
    return sources
```

## Living Tsunami - Design Specification

### Card Text
> "Once per turn, before performing an Attack action, you may move 1 space."

### Breakdown

| Component | Interpretation |
|-----------|----------------|
| "Once per turn" | Usage limit: 1 per hero's turn, resets at turn end |
| "before performing an Attack action" | Trigger: `BEFORE_ATTACK` (primary or secondary) |
| "you may" | Optional - requires player confirmation |
| "move 1 space" | Effect: `MoveSequenceStep(range_val=1)` |

### When It Triggers

The passive triggers whenever:
- The hero is Level 8+ (ultimate unlocked)
- The hero chooses ATTACK as their action (primary OR secondary)
- The passive hasn't been used this turn yet
- The player confirms they want to use it

---

## Architecture

### New Components

#### 1. `PassiveTrigger` Enum
```python
class PassiveTrigger(str, Enum):
    """When passive abilities activate."""
    BEFORE_ATTACK = "before_attack"
    BEFORE_MOVEMENT = "before_movement"
    BEFORE_SKILL = "before_skill"
    # AFTER_* triggers deferred for future implementation
```

#### 2. `PassiveConfig` Model
```python
class PassiveConfig(BaseModel):
    """Configuration for a card's passive ability."""
    trigger: PassiveTrigger
    uses_per_turn: int = 1       # -1 = unlimited
    is_optional: bool = True     # "you may" - requires confirmation
    prompt: str = ""             # UI prompt for the choice
```

#### 3. Extended `CardEffect` Base Class
```python
class CardEffect(ABC):
    # Existing methods...
    def get_steps(...) -> List[GameStep]: ...
    def get_defense_steps(...) -> Optional[List[GameStep]]: ...
    def get_on_block_steps(...) -> List[GameStep]: ...
    
    # New methods for passives
    def get_passive_config(self) -> Optional[PassiveConfig]:
        """Returns passive config if this card has a passive ability."""
        return None
    
    def get_passive_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: Dict[str, Any],
    ) -> List[GameStep]:
        """Returns steps to execute when this passive triggers."""
        return []
```

### New Steps

#### `CheckPassiveAbilitiesStep`
Scans hero's active cards for matching passives and spawns offer steps.

```
Input: trigger (PassiveTrigger)
Logic:
  1. Get current actor's active passive sources:
     - Regular cards: played_cards where RESOLVED + face-up
     - Ultimate: if hero.level >= 8
  2. For each source with matching trigger:
     - Check usage limit not exceeded
     - Spawn OfferPassiveStep
Output: List of OfferPassiveStep
```

#### `OfferPassiveStep`
Presents optional choice to player, or auto-executes if mandatory.

```
Input: card_id, trigger, is_optional, prompt
Logic:
  1. If not optional: execute passive steps immediately
  2. If optional: request YES/NO input from player
  3. If YES: spawn passive steps + MarkPassiveUsedStep
  4. If NO: do nothing
Output: Passive steps or empty
```

#### `MarkPassiveUsedStep`
Increments usage counter after passive is used.

```
Input: card_id
Logic: card.passive_uses_this_turn += 1
Output: None
```

### Integration Points

#### In `ResolveCardStep`
When player selects an action, insert passive check BEFORE the action:

```python
# Current flow:
# Player chooses ATTACK → spawn AttackSequenceStep

# New flow:
# Player chooses ATTACK → spawn [CheckPassiveAbilitiesStep(BEFORE_ATTACK), AttackSequenceStep]
```

#### In `FinalizeHeroTurnStep`
Reset passive usage counters at turn end:

```python
# Reset usage for regular cards
for card in hero.played_cards:
    card.passive_uses_this_turn = 0

# Reset usage for ultimate (if tracking needed)
if hero.ultimate_card:
    hero.ultimate_card.passive_uses_this_turn = 0
```

---

## Implementation Steps

### Phase 1: Core Infrastructure

| Step | File | Changes |
|------|------|---------|
| 1.1 | `domain/models/enums.py` | Add `PassiveTrigger` enum |
| 1.2 | `domain/models/card.py` | Add `passive_uses_this_turn: int = 0` field |
| 1.3 | `domain/models/unit.py` | Add `ultimate_card: Optional[Card] = None` field to Hero |
| 1.4 | `engine/effects.py` | Add `PassiveConfig` model |
| 1.5 | `engine/effects.py` | Add `get_passive_config()` and `get_passive_steps()` to CardEffect |

### Phase 2: New Steps

| Step | File | Changes |
|------|------|---------|
| 2.1 | `engine/steps.py` | Add `CheckPassiveAbilitiesStep` |
| 2.2 | `engine/steps.py` | Add `OfferPassiveStep` |
| 2.3 | `engine/steps.py` | Add `MarkPassiveUsedStep` |

### Phase 3: Integration

| Step | File | Changes |
|------|------|---------|
| 3.1 | `engine/steps.py` | Modify `ResolveCardStep` to insert passive checks |
| 3.2 | `engine/steps.py` | Modify `FinalizeHeroTurnStep` to reset usage counters |

### Phase 4: Living Tsunami Implementation

| Step | File | Changes |
|------|------|---------|
| 4.1 | `data/heroes/arien.py` | Store ultimate card separately (not in deck) |
| 4.2 | `scripts/arien_effects.py` | Implement `LivingTsunamiEffect` with passive config |

### Phase 5: Testing

| Test | Description |
|------|-------------|
| Passive triggers before attack | Living Tsunami offers move before AttackSequenceStep |
| Usage limit enforced | Only triggers once per turn |
| Optional decline works | Player can say "NO" and skip |
| Level gate works | Only active at Level 8+ |
| Works for secondary attack | Triggers for both primary and secondary Attack |
| Resets at turn end | Usage counter resets in FinalizeHeroTurnStep |

---

## Files to Modify/Create

| File | Action | Description |
|------|--------|-------------|
| `src/goa2/domain/models/enums.py` | Modify | Add `PassiveTrigger` enum |
| `src/goa2/domain/models/card.py` | Modify | Add `passive_uses_this_turn` field |
| `src/goa2/domain/models/unit.py` | Modify | Add `ultimate_card` field to Hero |
| `src/goa2/engine/effects.py` | Modify | Add `PassiveConfig` + new CardEffect methods |
| `src/goa2/engine/steps.py` | Modify | Add 3 new steps + integration |
| `src/goa2/data/heroes/arien.py` | Modify | Configure ultimate card properly |
| `src/goa2/scripts/arien_effects.py` | Modify | Implement `LivingTsunamiEffect` |
| `tests/engine/test_living_tsunami.py` | Create | New test file |

---

## Example: LivingTsunamiEffect Implementation

```python
@register_effect("living_tsunami")
class LivingTsunamiEffect(CardEffect):
    """
    Ultimate (Purple) - Arien
    
    Card text: "Once per turn, before performing an Attack action, 
    you may move 1 space."
    
    This is a passive ability that triggers BEFORE_ATTACK.
    As an ultimate, it's always active once the hero reaches Level 8.
    """
    
    def get_passive_config(self) -> Optional[PassiveConfig]:
        return PassiveConfig(
            trigger=PassiveTrigger.BEFORE_ATTACK,
            uses_per_turn=1,
            is_optional=True,
            prompt="Living Tsunami: Move 1 space before attacking?",
        )
    
    def get_passive_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: Dict[str, Any],
    ) -> List[GameStep]:
        return [
            MoveSequenceStep(
                unit_id=hero.id,
                range_val=1,
                is_mandatory=False,  # "you may move" - can stay in place
            )
        ]
```

---

## Future Considerations

### AFTER_* Triggers
Currently deferred. When needed, add:
- `AFTER_ATTACK`, `AFTER_MOVEMENT`, `AFTER_SKILL` to `PassiveTrigger`
- Insert `CheckPassiveAbilitiesStep` after action steps in `ResolveCardStep`

### Multiple Passives
If a hero has multiple passive sources that trigger at the same time:
- Process in card play order (oldest first)
- Each gets its own `OfferPassiveStep`

### Conditional Passives
Some passives may have additional conditions (e.g., "if adjacent to enemy"):
- Add optional `condition` field to `PassiveConfig`
- Check condition in `CheckPassiveAbilitiesStep` before spawning offer

---

## Estimated Complexity

| Component | Lines of Code | Complexity |
|-----------|---------------|------------|
| PassiveTrigger enum | ~10 | Low |
| Card field | ~2 | Low |
| Hero ultimate_card field | ~5 | Low |
| PassiveConfig + CardEffect extensions | ~50 | Medium |
| 3 new steps | ~120 | Medium |
| ResolveCardStep modification | ~20 | Low |
| FinalizeHeroTurnStep modification | ~10 | Low |
| LivingTsunamiEffect | ~30 | Low |
| Tests | ~200 | Medium |

**Total:** ~450 lines of new/modified code
