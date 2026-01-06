# GoA2 Backend TODO

Outstanding features and extensions needed to support the full card library.

---

## Priority 1: Core Extensions

### 1.1 May Repeat Once Pattern
**Status:** Not Started  
**Effort:** Medium (3-5 days)  
**Cards:** Seismic Slam, Backstab with Ballista, many others

Implement `MayRepeatOnceStep` to handle "May repeat once on a different target" patterns.

**Requirements:**
- [ ] `MayRepeatOnceStep` - wraps effect steps, asks player to confirm repeat
- [ ] `RecordTargetStep` - tracks selected targets in execution context
- [ ] `AskRepeatStep` - confirmation input request
- [ ] `ExcludeIDsFilter` - filter out previously targeted entities
- [ ] `PREVENT_ACTION_REPEAT` modifier support in ValidationService

**Design:**
```python
MayRepeatOnceStep(
    effect_steps_fn=lambda ctx: [...],
    restriction="different_target",  # or "different_enemy_hero", "none"
    max_repeats=1
)
```

---

### 1.2 Targeting Prevention (Smoke Bomb)
**Status:** Not Started  
**Effort:** Medium (3-5 days)  
**Cards:** Smoke Bomb, concealment effects

Implement line-of-sight blocking for targeting.

**Requirements:**
- [ ] `ValidationService.can_be_targeted(state, attacker_id, target_id)` method
- [ ] `TARGET_PREVENTION` effect type with line-of-sight check
- [ ] Hex geometry: `is_on_line_between(hex_a, hex_b, blocking_hex)` utility
- [ ] Token-based blocking (Smoke Bomb token on straight line)

---

### 1.3 Card Tier Exception for Prevention
**Status:** Not Started  
**Effort:** Small (1 day)  
**Cards:** Spell Break ("except on gold cards")

Allow prevention effects to have exceptions based on card tier.

**Requirements:**
- [ ] Add `except_card_tiers: List[CardTier] = []` to Modifier model
- [ ] Update ValidationService to check current card tier against exceptions
- [ ] Pass `current_card_tier` in context during card resolution

---

### 1.4 Fast Travel Prevention
**Status:** Partially Done  
**Effort:** Small (1 day)  
**Cards:** Slippery Ground, Deluge, Grasping Roots, etc.

Complete fast travel prevention validation.

**Requirements:**
- [ ] `ValidationService.can_fast_travel()` method (in plan but not implemented)
- [ ] Check in `FastTravelStep` before allowing travel
- [x] `PREVENT_FAST_TRAVEL` status tag defined

---

## Priority 2: Medium Extensions

### 2.1 Cancel Active Effects
**Status:** Not Started  
**Effort:** Medium (2-3 days)  
**Cards:** Disruptor Pulse, Disruptor Grid

Cancel (remove) effects from enemy units.

**Requirements:**
- [ ] `CancelEffectsStep` - removes effects matching criteria
- [ ] Track which effects came from which action type (skill vs attack)
- [ ] Filter by source team, effect type, or specific source_id

---

### 2.2 Player Choice / Forced Decisions
**Status:** Not Started  
**Effort:** Medium (3-4 days)  
**Cards:** Lesser Evil, Greater Good, X Marks the Spot, Dead Man's Hand

Framework for "Enemy hero chooses one" patterns.

**Requirements:**
- [ ] `PlayerChoiceStep` - presents options to target player (not actor)
- [ ] Each option is a list of sub-steps
- [ ] Handle "any option can be chosen, even if no effect"
- [ ] Support mandatory choices ("discards a card, or is defeated")

**Design:**
```python
PlayerChoiceStep(
    choosing_player_id="enemy_hero_id",
    options=[
        ChoiceOption(label="Discard a card", steps=[DiscardCardStep(...)]),
        ChoiceOption(label="Hero is defeated", steps=[DefeatHeroStep(...)])
    ],
    is_mandatory=True  # Must choose one
)
```

---

### 2.3 Reverse Initiative Order
**Status:** Not Started  
**Effort:** Medium (2-3 days)  
**Cards:** Reverse Time, Tear in Time

Heroes with lower initiative act before higher.

**Requirements:**
- [ ] Flag in GameState: `initiative_reversed: bool = False`
- [ ] Modifier with `status_tag="REVERSE_INITIATIVE"` (global effect)
- [ ] Update `FindHighestInitiativeStep` to check flag and invert sort
- [ ] Ensure it applies "next turn" correctly

---

### 2.4 Dynamic/Conditional Obstacles (Static Barrier)
**Status:** Not Started  
**Effort:** Medium-Large (4-5 days)  
**Cards:** Static Barrier

Spaces count as obstacles based on actor position.

**Requirements:**
- [ ] Pathfinding/obstacle checks need `actor_id` parameter
- [ ] `ConditionalObstacleEffect` that defines condition function
- [ ] Board queries check active effects for dynamic obstacles

---

### 2.5 Card-Level Modifiers (Hurry Up!)
**Status:** Not Started  
**Effort:** Medium (2-3 days)  
**Cards:** Hurry Up!

Modify properties of unresolved cards.

**Requirements:**
- [ ] Decide: Modifiers target cards, OR temporarily mutate card object?
- [ ] "Set printed Initiative to 11" - affects turn order
- [ ] Track modified cards and revert when card state changes

---

## Priority 3: Major Extensions

### 3.1 Board Partition (Crack in Reality)
**Status:** Not Started  
**Effort:** Large (1-2 weeks)  
**Cards:** Crack in Reality, Shift Reality

Split board into two sides; units cannot interact across the line.

**Requirements:**
- [ ] `BoardPartition` model with line definition
- [ ] Method: `get_partition_side(hex)` returns which side
- [ ] All target validation checks partition
- [ ] All pathfinding respects partition
- [ ] Radius effects only apply to same-side hexes
- [ ] Duration: THIS_TURN

**Complexity:** This affects targeting, movement, pathfinding, radius calculations. Consider if this is MVP or later.

---

### 3.2 Ultimate Trick (Control Another Hero)
**Status:** Not Started  
**Effort:** Large (1 week)  
**Cards:** The Ultimate Trick

Actor chooses another hero's action and how it's performed.

**Requirements:**
- [ ] Override `current_actor_id` temporarily for action selection
- [ ] Pass control to actor for all input requests
- [ ] Target hero's card is resolved but actor makes decisions
- [ ] Complex edge cases with reactions

---

## Priority 4: Minor Features

### 4.1 Adjacent-to-Terrain Filter
**Status:** Not Started  
**Effort:** Small (half day)  
**Cards:** Seismic Slam, Bear Trap, Deadfall Trap

Filter units that are adjacent to terrain/obstacles.

**Requirements:**
- [ ] `AdjacentToTerrainFilter` - checks if any neighbor hex is terrain
- [ ] `AdjacentToTokenFilter(token_type)` - checks for specific token adjacency

---

### 4.2 Discard Card Step
**Status:** Not Started  
**Effort:** Small (half day)  
**Cards:** Many (Lesser Evil, Bear Trap, etc.)

Force a hero to discard a card.

**Requirements:**
- [ ] `DiscardCardStep(target_hero_id, is_mandatory, choice_by)` 
- [ ] If `choice_by="target"` - target chooses which card
- [ ] If `choice_by="actor"` - actor chooses
- [ ] Handle "discard, if able" (optional)

---

### 4.3 Place Token Step
**Status:** Not Started  
**Effort:** Small (half day)  
**Cards:** Rock placement, Smoke Bomb, Ice tokens

Generic step to place tokens on the board.

**Requirements:**
- [ ] `PlaceTokenStep(token_type, at_hex, at_context_key)`
- [ ] Token model and tracking in GameState
- [ ] Token expiration (duration-based)

---

### 4.4 Swap Resolved Cards
**Status:** Not Started  
**Effort:** Small (1 day)  
**Cards:** Diabolical Laughter, Time Warp

Swap cards between hand/resolved/unresolved states.

**Requirements:**
- [ ] `SwapResolvedCardsStep(hero_id, card_a_id, card_b_id)`
- [ ] Handle "without canceling active effects" flag
- [ ] Validate card states before swap

---

## Completed Features ✅

- [x] Effect System (Phase 1-6 complete)
- [x] ValidationService core methods
- [x] Modifier with source_card_id
- [x] ActiveEffect with spatial scope
- [x] PLACEMENT_PREVENTION (Magnetic Dagger)
- [x] MOVEMENT_ZONE (Slippery Ground)
- [x] CreateModifierStep / CreateEffectStep
- [x] CanBePlacedByActorFilter

---

## Implementation Order Recommendation

1. **Fast Travel Prevention** (1.4) - nearly done, quick win
2. **May Repeat Once** (1.1) - enables many cards
3. **Discard Card Step** (4.2) - simple, enables many cards
4. **Player Choice / Forced Decisions** (2.2) - enables choice cards
5. **Card Tier Exception** (1.3) - small, enables Spell Break pattern
6. **Targeting Prevention** (1.2) - Smoke Bomb and similar
7. Remaining items based on priority
