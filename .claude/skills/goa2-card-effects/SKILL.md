---
name: goa2-card-effects
description: Comprehensive guide for implementing card effects in the Guards of Atlantis II (GoA2) engine. Use this when implementing hero abilities, card logic, or game mechanics.
---

# GoA2 Card Effect Implementation Guide

This skill provides the patterns, API reference, and best practices for implementing card logic in the GoA2 Python engine.

## Core Architecture: "Logic as Data"

The engine uses a **Step Stack** system. Card effects do **not** execute logic directly; they return a list of `GameStep` objects (data) that the engine executes sequentially.

1.  **CardEffect**: A stateless factory that returns steps.
2.  **GameStep**: Atomic unit of logic (e.g., "Select Unit", "Deal Damage", "Move").
3.  **Context**: A shared dictionary passed between steps. Step A writes to `context["target_id"]`, Step B reads from it.

## The Golden Path Template

**IMPORTANT**: The method is `build_steps()` NOT `get_steps()`. Stats are pre-computed and passed as a parameter.

```python
from typing import List, TYPE_CHECKING, Optional
from goa2.engine.effects import CardEffect, register_effect, PassiveConfig
from goa2.engine.steps import (
    GameStep, AttackSequenceStep, SelectStep, PushUnitStep,
    PlaceUnitStep, SwapUnitsStep, CreateModifierStep, CreateEffectStep,
    MayRepeatOnceStep, ForceDiscardStep, DefeatUnitStep,
    CheckAdjacencyStep, CheckUnitTypeStep, CombineBooleanContextStep,
    SetContextFlagStep, CountStep, CheckContextConditionStep, RetrieveCardStep,
)
from goa2.engine.filters import (
    RangeFilter, TeamFilter, ImmunityFilter, ObstacleFilter, UnitTypeFilter,
    NotInStraightLineFilter, LineBehindTargetFilter, AdjacencyToContextFilter,
    RelativeDistanceFilter,
)
from goa2.engine.stats import CardStats
from goa2.domain.models import (
    StatType, DurationType, EffectType, Shape, AffectsFilter, ActionType, CardColor
)
from goa2.domain.models.enums import TargetType, PassiveTrigger

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card

@register_effect("your_effect_id")
class YourEffectName(CardEffect):
    """
    Card Text: "Target a unit in range. Attack 4. Push it 2 spaces."
    """
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        # Stats are pre-computed (handles buffs/debuffs automatically)
        return [
            # Example: Attack -> Push
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                target_id_key="victim_id"  # Stores selected target in context
            ),
            PushUnitStep(
                target_key="victim_id",
                distance=2
            )
        ]
```

## Method Reference

### Primary Action Cards (Attack/Skill/Movement)
```python
def build_steps(
    self,
    state: GameState,
    hero: Hero,
    card: Card,
    stats: CardStats,
) -> List[GameStep]:
    """Return steps for card's primary action on your turn."""
```

### Defense Cards (Primary DEFENSE)
```python
def build_defense_steps(
    self,
    state: GameState,
    defender: Hero,
    card: Card,
    stats: CardStats,
    context: Dict[str, Any],
) -> Optional[List[GameStep]]:
    """
    Return steps when used as primary DEFENSE in reaction.
    Context contains: attack_is_ranged, attacker_id, defender_id
    Return None to fall back to build_steps().
    """
```

### "If You Do" Effects (After Block)
```python
def build_on_block_steps(
    self,
    state: GameState,
    defender: Hero,
    card: Card,
    stats: CardStats,
    context: Dict[str, Any],
) -> List[GameStep]:
    """Return steps after successful block ('if you do' effects)."""
```

### Passive Abilities (Ultimate/Persistent)
```python
def get_passive_config(self) -> Optional[PassiveConfig]:
    """Return passive configuration, or None if no passive."""
    return PassiveConfig(
        trigger=PassiveTrigger.BEFORE_ATTACK,
        uses_per_turn=1,  # 0 = unlimited
        is_optional=True,
        prompt="Use passive?",
    )

def should_offer_passive(
    self,
    state: GameState,
    hero: Hero,
    card: Card,
    trigger: PassiveTrigger,
    context: Dict[str, Any],
) -> bool:
    """
    Optional runtime gate. Default: True. Override when the trigger
    fires broadly but this passive only cares about a subset — e.g.
    Battle Fury listens for AFTER_CARD_DISCARD but only when the
    discard_source was PLAYED. Returning False skips the offer
    entirely (no prompt shown to the player).
    """
    return True

def get_passive_steps(
    self,
    state: GameState,
    hero: Hero,
    card: Card,
    trigger: PassiveTrigger,
    context: Dict[str, Any],
) -> List[GameStep]:
    """Return steps when passive triggers."""
    return []
```

**Important — broad triggers need a gate, not a `get_passive_steps` early-return.**
A passive's config only matches on trigger name. If a trigger fires broadly
(e.g. `AFTER_CARD_DISCARD` fires on every discard), and you filter by
returning `[]` from `get_passive_steps`, the player still gets prompted
YES/NO first — bad UX. Filter in `should_offer_passive` instead so the
offer is never created.

## Interpreting Card Text

Card text is a lossy compression of the rules. Translate the phrasing to mechanics with
the rules below **before** wiring steps — several common phrasings map to a structure that
is *not* the obvious one. Definitions here are from the GoA2 rulebook glossary.

### Execution rules (apply to every card)

- **Order is exact.** Apply the card text in the order written.
- **Stop on failure.** If a *mandatory* step cannot complete, stop there and **skip all
  remaining steps**.
- **What is mandatory:** only steps containing **"you may"**, **"up to"**, or **"if able"**
  are non-mandatory; **everything else is mandatory**. ("if able" at the *end* of a sentence
  makes only the preceding clause optional; at the *start*, the whole sentence.)
- **Who chooses:** *you* (the actor) make every choice in your card's text, **unless** the
  text hands a choice to another hero. E.g. "an enemy hero in radius discards a card, if
  able" → you choose which enemy hero; that hero chooses which card. "A hero in range" ≡
  "Target a hero in range".

### Phrasing → mechanics cheat sheet

| Card phrasing | Means | Implement with | Don't |
|---|---|---|---|
| **"each X does Y"** / **"all X"** | All matching, **mandatory**, no actor choice | `CollectUnitsStep` → `ForEachStep` → Y | `MultiSelectStep` (that's a *choice*) |
| **"up to N X do Y"** | Cap N, **optional** (0…N), actor picks | `MultiSelectStep(min_selections=0, max_selections=N)` or N sequential optional selects | min=N / treating as required |
| **"…up to N…" where Y can change immunity** | Defeats/removals alter heavy support → immunity must be re-checked between picks | **Sequential** select+action pairs (each re-runs `ImmunityFilter`) | One `MultiSelect` — it snapshots immunity once |
| **"discards a card, or is defeated"** | One **victim-driven** outcome (discard if able, else defeat) | `ForceDiscardOrDefeatStep(victim_key=…)` | An A/B chooser for the *actor* |
| **"discards a card"** (no "or defeated") | Discard if able, else nothing | `ForceDiscardStep` | — |
| **"Choose one — A / B"** (modal bullets) | Exactly one bullet; ignore the rest | `SelectStep(TargetType.NUMBER)` + `CheckContextConditionStep` branch | — |
| **"Choose one, or both / twice / up to X"** | Multiple bullets allowed; **any order** unless stated; treat as one action | optional block per bullet; `ExcludeIdentityFilter` if "different targets" | Forcing a fixed bullet order |
| **"Repeat" / "Repeat once / up to X"** | Perform the *entire* action again, same range/restrictions; can't repeat a repeat; one active-effect instance per card | `MayRepeatOnceStep` / `MayRepeatNTimesStep` | Duplicating active effects on repeat |
| **"Remove a/your X. [Effect]"** | Removal is a **cost** gating the effect (no X → no effect) | mandatory `SelectStep` for X → `RemoveTokenStep` → effect | Running the effect when nothing was removed |
| **"If you move in a straight line: …"** | Emergent condition on *how* you move, not a prompt; riders ("may ignore obstacles") share the condition | resolve the move, then gate riders on `BetweenHexesFilter(origin→dest)` (empty unless straight) | A "use ability?" yes/no |
| **"regardless of immunity"** | Override — include immune/heavy units | `skip_immunity_filter=True` | Leaving the default immunity filter on |
| **"a unit adjacent to a [token/unit]"** | Targeting anchored on proximity (a *presence check*, doesn't target the token) | `CountMatchFilter` (see Filter Library) | A bespoke adjacency filter |

### Verb precision (easy to conflate)

- **Place** — put a piece into an **empty** space; **not movement**. For tokens: take from
  supply; if supply is exhausted, first remove that many tokens of the same type from the
  board (`PlaceTokenStep` does this automatically).
- **Remove** — take a piece off the board; **no coins**.
- **Defeat** — remove an enemy unit **and collect coins**; never a friendly unit.
- **Replace** — swap a board object with a **different** object.
- **Swap** — two board objects trade places; **not** movement or placement (`SwapUnitsStep`).
- **Push** — move in a straight line directly away; partial pushes allowed (can be 0).

### Immunity, targeting, and "self"

- **Immune** units can't be targeted/affected — **unless** the text overrides
  ("regardless of immunity"). You are **never** immune to your own actions.
- **Presence checks count immune units.** "if you are adjacent to a minion" counts immune
  minions, and does **not** target. (Our `CountMatchFilter` tree-adjacency is a presence
  check — correct, it doesn't target the token.)
- Units that **ignore obstacles** move *through* immune units and tokens.
- **"A friendly unit" never includes you.** Auto-self-exclusion on `SelectStep` matches
  this. A card affects your own hero only if it says so explicitly.
- **Spatial words → stats:** "adjacent to you" = range 1; "in range" = card `range`; "in
  radius" = card `radius` (a card has one or the other, never both). An active effect's
  radius is measured from your **current** space (it moves with you).

### Before you build, then verify on a real round

Confirm the facts the card text does **not** state: token/marker board behavior (all tokens
are obstacles), **supply count**, **end-of-round persistence**, cost-vs-independent,
immunity applicability, and **effect timing/lifecycle** (see "Effect Lifecycle Gotcha"
under Duration Types). Then drive at least one effect through the real `EndPhaseStep`/turn
flow — "each/all", cost, and lifecycle bugs pass isolated unit tests while being broken in
play.

## Recipe Cookbook

### 1. Attacks
**Basic Attack** (Selections & Reactions handled automatically by `AttackSequenceStep`):
```python
AttackSequenceStep(damage=stats.primary_value, range_val=stats.range)
```

**Attack Adjacent** (Hardcoded range - not buffable):
```python
AttackSequenceStep(damage=stats.primary_value, range_val=1)
```

**Attack with targeting restrictions** (e.g., "not in a straight line"):
```python
AttackSequenceStep(
    damage=stats.primary_value,
    range_val=stats.range,
    target_filters=[NotInStraightLineFilter()],
)
```

### 2. Movement & Positioning
**Movement Action** (Primary/Secondary - triggers movement limits):
```python
MoveSequenceStep(unit_id=hero.id, range_val=stats.primary_value)
```

**Teleport / Place**:
```python
SelectStep(
    target_type=TargetType.HEX,
    prompt="Select destination",
    output_key="dest_hex",
    filters=[
        RangeFilter(max_range=stats.range),
        ObstacleFilter(is_obstacle=False),
        SpawnPointFilter(has_spawn_point=False),
    ]
)
PlaceUnitStep(unit_id=hero.id, destination_key="dest_hex")
```

**Push Unit**:
```python
# Push target stored in 'victim_id' by 2 spaces
PushUnitStep(target_key="victim_id", distance=2)
```

**Push with variable distance** (read from context):
```python
# First select distance
SelectStep(
    target_type=TargetType.NUMBER,
    prompt="Choose push distance",
    output_key="push_distance",
    number_options=[3, 4],
)
# Then push
PushUnitStep(
    target_key="victim_id",
    distance_key="push_distance",  # Read from context
    collision_output_key="collision",  # Store result
)
```

**Swap Units**:
```python
SelectStep(
    target_type=TargetType.UNIT,
    prompt="Select unit to swap with",
    output_key="swap_target",
    filters=[RangeFilter(max_range=stats.range)],
)
SwapUnitsStep(unit_a_id=hero.id, unit_b_key="swap_target")
```

**Orbit Movement** (maintain distance from origin):
```python
SelectStep(
    target_type=TargetType.HEX,
    prompt="Select orbit destination",
    output_key="orbit_dest",
    filters=[
        AdjacencyToContextFilter(target_key="orbit_target"),
        RelativeDistanceFilter(reference_key="orbit_target", operator="=="),
    ],
)
PlaceUnitStep(unit_key="orbit_target", destination_key="orbit_dest")
```

**Push-Farther Movement** (move target 1 space farther away from you):
```python
SelectStep(
    target_type=TargetType.HEX,
    prompt="Select a space farther away from you",
    output_key="push_dest",
    filters=[
        RelativeDistanceFilter(reference_key="defender_id", operator=">"),
        AdjacencyToContextFilter(target_key="defender_id"),
        ObstacleFilter(is_obstacle=False),
    ],
    is_mandatory=False,
)
MoveUnitStep(unit_key="defender_id", destination_key="push_dest", active_if_key="push_dest")
```

### 3. Buffs & Debuffs
**Stat Modifier** (e.g., Venom Strike: -1 Defense this round):
```python
CreateModifierStep(
    target_key="victim_id",
    stat_type=StatType.DEFENSE,
    value_mod=-1,
    duration=DurationType.THIS_ROUND
)
```

**Status Tag** (e.g., Root, Silence):
```python
CreateModifierStep(
    target_key="victim_id",
    status_tag="root",
    duration=DurationType.THIS_TURN
)
```

### 4. Zone Effects (Auras/Hazards)
**Movement Restriction Zone** (e.g., Slippery Ground):
```python
CreateEffectStep(
    effect_type=EffectType.MOVEMENT_ZONE,
    scope=EffectScope(
        shape=Shape.ADJACENT,
        origin_id=hero.id,
        affects=AffectsFilter.ENEMY_HEROES
    ),
    duration=DurationType.THIS_TURN,
    max_value=1,  # Limit movement to 1 hex
    limit_actions_only=True,  # Allow pushes/effects to exceed limit
    restrictions=[ActionType.FAST_TRAVEL],  # Block Fast Travel
)
```

**Placement Prevention** (e.g., Magnetic Dagger):
```python
CreateEffectStep(
    effect_type=EffectType.PLACEMENT_PREVENTION,
    scope=EffectScope(
        shape=Shape.RADIUS,
        range=3,
        origin_id=hero.id,
        affects=AffectsFilter.ENEMY_HEROES
    ),
    duration=DurationType.THIS_TURN,
    displacement_blocks=[DisplacementType.PLACE, DisplacementType.SWAP],
    blocks_enemy_actors=True,
    blocks_self=False,
)
```

**Target Prevention** (e.g., Spell Break):
```python
CreateEffectStep(
    effect_type=EffectType.TARGET_PREVENTION,
    scope=EffectScope(
        shape=Shape.RADIUS,
        range=3,
        origin_id=hero.id,
        affects=AffectsFilter.ENEMY_HEROES
    ),
    duration=DurationType.THIS_TURN,
    restrictions=[ActionType.SKILL],
    except_card_colors=[CardColor.GOLD],  # Gold cards still work
)
```

**Attack Immunity** (e.g., Master Duelist):
```python
CreateEffectStep(
    effect_type=EffectType.ATTACK_IMMUNITY,
    scope=EffectScope(
        shape=Shape.POINT,
        origin_id=defender.id,
        affects=AffectsFilter.SELF
    ),
    duration=DurationType.THIS_ROUND,
    except_attacker_key="attacker_id",  # Current attacker exempted
    is_active=True,
)
```

**Full Action Immunity** (e.g., Death Seeker — immune to ALL enemy actions, like heavy minions):
```python
CreateEffectStep(
    effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
    source_id=hero.id,
    duration=DurationType.THIS_ROUND,
    is_active=True,
)
```
Note: `IMMUNITY_ENEMY_ACTIONS` is checked by `is_immune()` in `rules.py`, same as heavy minion immunity. This blocks attacks, skills, and all targeting — not just attacks.

### 5. Discard & Defeat
**Force Discard** (if no cards, no penalty):
```python
ForceDiscardStep(victim_key="victim_id")
```

**Force Discard OR Defeat** (if no cards, must defeat):
```python
ForceDiscardOrDefeatStep(victim_key="victim_id")
```

**Defeat Specific Unit**:
```python
DefeatUnitStep(victim_id="minion_1")
```

**Conditional Defeat** (only if victim has no cards):
```python
ForceDiscardOrDefeatStep(
    victim_key="victim_id",
    active_if_key="target_has_no_cards"
)
```

### 6. Defense Cards
**Ranged-Only Block** (e.g., Stop Projectiles):
```python
def build_defense_steps(self, state, defender, card, stats, context):
    if context.get("attack_is_ranged"):
        return [SetContextFlagStep(key="auto_block", value=True)]
    else:
        return [SetContextFlagStep(key="defense_invalid", value=True)]
```

**Block with "If You Do" Effect** (e.g., Reflect Projectiles):
```python
def build_defense_steps(self, state, defender, card, stats, context):
    if context.get("attack_is_ranged"):
        return [SetContextFlagStep(key="auto_block", value=True)]
    return [SetContextFlagStep(key="defense_invalid", value=True)]

def build_on_block_steps(self, state, defender, card, stats, context):
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

**Ignore Minion Defense** (e.g., Aspiring Duelist):
```python
def build_defense_steps(self, state, defender, card, stats, context):
    return [SetContextFlagStep(key="ignore_minion_defense", value=True)]
```

### 7. Repeatable Logic
**May Repeat Once**:
```python
MayRepeatOnceStep(
    prompt="Repeat action on a different target?",
    steps_template=[
        SelectStep(
            target_type=TargetType.UNIT,
            filters=[
                TeamFilter(relation="ENEMY"),
                ExcludeIdentityFilter(exclude_keys=["first_target_id"]),
            ],
            output_key="second_target_id",
        ),
        AttackSequenceStep(target_id_key="second_target_id", damage=3),
    ],
)
```

**May Repeat N Times**:
```python
MayRepeatNTimesStep(
    max_repeats=2,
    prompt="Repeat orbit?",
    steps_template=[...],
)
```

**Conditional Repeat** (e.g., Ebb and Flow - "if adjacent"):
```python
CheckAdjacencyStep(
    unit_a_id=hero.id,
    unit_b_key="swap_target_1",
    output_key="can_repeat",
)
MayRepeatOnceStep(
    active_if_key="can_repeat",
    steps_template=[...],
)
```

**Repeat on Same Target**:
```python
orbit_steps = [
    SelectStep(...),
    PlaceUnitStep(unit_key="orbit_target", destination_key="orbit_dest"),
]
return steps + orbit_steps + [MayRepeatOnceStep(steps_template=orbit_steps)]
```

### 8. Multi-Target Operations
**Select Multiple Units**:
```python
MultiSelectStep(
    target_type=TargetType.UNIT,
    prompt="Select up to 2 enemies",
    output_key="push_targets",
    max_selections=2,
    min_selections=0,  # Optional
    is_mandatory=False,
    filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
)
```

**Process Each Selected Unit**:
```python
ForEachStep(
    list_key="push_targets",
    item_key="current_target",
    steps_template=[
        PushUnitStep(target_key="current_target", distance=3),
    ],
)
```

**Combined Conditions** (e.g., Kinetic Repulse - collision AND is hero):
```python
ForEachStep(
    list_key="push_targets",
    item_key="current_target",
    steps_template=[
        PushUnitStep(
            target_key="current_target",
            distance=3,
            collision_output_key="collision",
        ),
        CheckUnitTypeStep(
            unit_key="current_target",
            expected_type="HERO",
            output_key="is_hero",
        ),
        CombineBooleanContextStep(
            key_a="collision",
            key_b="is_hero",
            output_key="should_discard",
            operation="AND",
        ),
        ForceDiscardStep(victim_key="current_target", active_if_key="should_discard"),
    ],
)
```

### 9. Card Manipulation
**Discard Specific Card**:
```python
DiscardCardStep(card_id="card_123", hero_id=hero_arien)
```

**Force Player to Choose Card to Discard**:
```python
SelectStep(
    target_type=TargetType.CARD,
    prompt="Select a card to discard",
    output_key="card_to_discard",
    card_container=CardContainerType.HAND,
    context_hero_id_key="victim_id",  # Look at victim's hand
    override_player_id_key="victim_id",  # Victim chooses
    is_mandatory=True,
)
DiscardCardStep(card_key="card_to_discard", hero_key="victim_id")
```

### 10. Counting & Conditional Checks
**Count units matching filters** (e.g., "if adjacent to an enemy"):
```python
# Count enemies adjacent to actor, store count in context
CountStep(
    target_type=TargetType.UNIT,
    filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
    output_key="adjacent_enemy_count",
)
```

**Check a context value against a threshold**:
```python
# Stores True in context if count >= 1, else stores None (for active_if_key compat)
CheckContextConditionStep(
    input_key="adjacent_enemy_count",
    operator=">=",  # Supports: ">=", ">", "==", "<=", "<", "!="
    threshold=1,
    output_key="has_adjacent_enemy",
)
```

**Count + Check pattern** (precondition for optional steps):
```python
# 1. Count matching units
CountStep(
    target_type=TargetType.UNIT,
    filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
    output_key="adj_count",
),
# 2. Check threshold
CheckContextConditionStep(
    input_key="adj_count", operator=">=", threshold=1,
    output_key="has_adjacent",
),
# 3. Conditional step (only runs if condition met)
SelectStep(
    ...,
    active_if_key="has_adjacent",
),
```

**Note:** `CheckContextConditionStep` stores `True` when the condition passes and `None` when it fails. This is intentional — `active_if_key` skips steps when the value is `None`, not when it's `False`.

### 11. Card Retrieval
**Retrieve card from discard pile** (e.g., "retrieve a discarded card"):
```python
# 1. Let player select from discard
SelectStep(
    target_type=TargetType.CARD,
    card_container=CardContainerType.DISCARD,
    prompt="Select a discarded card to retrieve",
    output_key="retrieved_card",
    is_mandatory=False,
),
# 2. Move card from discard to hand (emits CARD_RETRIEVED event)
RetrieveCardStep(
    card_key="retrieved_card",
    active_if_key="retrieved_card",  # Skip if player chose SKIP
),
```

**Conditional retrieval** (e.g., "if adjacent to enemy, retrieve a card"):
```python
# Full pattern: Count → Check → Select → Retrieve
CountStep(
    target_type=TargetType.UNIT,
    filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
    output_key="adjacent_enemy_count",
),
CheckContextConditionStep(
    input_key="adjacent_enemy_count", operator=">=", threshold=1,
    output_key="has_adjacent_enemy",
),
SelectStep(
    target_type=TargetType.CARD,
    card_container=CardContainerType.DISCARD,
    prompt="Select a discarded card to retrieve",
    output_key="retrieved_card",
    is_mandatory=False,
    active_if_key="has_adjacent_enemy",
),
RetrieveCardStep(card_key="retrieved_card", active_if_key="retrieved_card"),
```

### 12. Opponent Choice (Enemy Selects)
**Force opponent to choose** (e.g., "target enemy hero discards a card of their choice"):
```python
SelectStep(
    target_type=TargetType.CARD,
    prompt="Choose a card to discard",
    output_key="card_to_discard",
    card_container=CardContainerType.HAND,
    context_hero_id_key="victim_id",        # Look at victim's hand
    override_player_id_key="victim_id",     # Victim's player chooses
    is_mandatory=True,
)
DiscardCardStep(card_key="card_to_discard", hero_key="victim_id")
```

**Key:** `override_player_id_key` routes the input request to the specified player instead of the active player. Use `context_hero_id_key` to scope which hero's cards/state are visible.

### 13. Branching with NUMBER Select
**Choose-one pattern** (e.g., "Choose: Attack 3 OR Move 2"):
```python
SelectStep(
    target_type=TargetType.NUMBER,
    prompt="Choose action",
    output_key="choice",
    number_options=[1, 2],
    number_labels={1: "Attack 3", 2: "Move 2"},
),
# Branch A
CheckContextConditionStep(
    input_key="choice", operator="==", threshold=1,
    output_key="chose_attack",
),
AttackSequenceStep(
    damage=3, range_val=stats.range,
    active_if_key="chose_attack",
),
# Branch B
CheckContextConditionStep(
    input_key="choice", operator="==", threshold=2,
    output_key="chose_move",
),
MoveSequenceStep(
    unit_id=hero.id, range_val=2,
    active_if_key="chose_move",
),
```

**Choose one or both** (with ultimate passive):
```python
# First choice
SelectStep(
    target_type=TargetType.NUMBER,
    prompt="Choose action",
    output_key="choice",
    number_options=[1, 2],
),
# ... execute first choice ...

# If ultimate is active, offer second option
if hero.ultimate_card and hero.ultimate_card.state == CardState.PASSIVE:
    steps.append(SelectStep(
        target_type=TargetType.NUMBER,
        prompt="Also perform second action? (Ultimate)",
        output_key="ult_choice",
        number_options=[1, 0],
        number_labels={1: "Yes", 0: "Skip"},
        is_mandatory=False,
    ))
    # ... execute second choice if chosen ...
```

### 14. Build-Time State Access
`build_steps()` receives `state` — use it for dynamic logic that depends on current game state:
```python
def build_steps(self, state, hero, card, stats):
    steps = [...]

    # Check ultimate card state at build time
    has_ult = (
        hero.ultimate_card is not None
        and hero.ultimate_card.state == CardState.PASSIVE
    )
    if has_ult:
        steps.append(...)  # Extra steps only with ultimate

    # Read board state for conditional logic
    hero_hex = state.entity_locations.get(hero.id)
    zone = state.board.get_zone_for_hex(hero_hex)

    return steps
```

**When to use build-time vs runtime checks:**
- **Build-time** (`if` in `build_steps`): Static conditions that won't change during resolution (ultimate active, card tier)
- **Runtime** (`active_if_key`, `CheckContextConditionStep`): Dynamic conditions that depend on step results (adjacency after movement, collision results)

### 15. Forced Defense Movement
**Force defender to use their movement card** (e.g., "defender must move in a straight line"):
```python
ForceDefenseCardMovementStep(
    target_key="victim_id",
    force_straight_line=True,    # Must move in straight line
    force_full_distance=True,    # Must use full movement value
)
```

Handles 3 cases automatically at runtime:
1. **No movement on defense card** → skip (no movement happens)
2. **Secondary MOVEMENT** → creates constrained `MoveSequenceStep`
3. **Primary MOVEMENT** → calls card effect's `build_steps()` and injects constraint flags

### 16. Constrained Movement
**Force straight-line, full-distance movement**:
```python
MoveSequenceStep(
    unit_id=hero.id,
    range_val=stats.primary_value,
    force_straight_line=True,   # Adds InStraightLineFilter + StraightLinePathFilter
    force_full_distance=True,   # Sets min_range = max_range
)
```

### 17. Utility Steps
**Move Another Unit** (forced movement, not action):
```python
SelectStep(
    target_type=TargetType.UNIT,
    prompt="Select unit to move",
    output_key="nudge_unit",
    filters=[
        AdjacencyToContextFilter(target_key="victim_id"),
        ExcludeIdentityFilter(exclude_keys=["victim_id"]),
        ForcedMovementByEnemyFilter(),  # Check if protected
    ],
)
SelectStep(
    target_type=TargetType.HEX,
    prompt="Select destination",
    output_key="nudge_dest",
    filters=[RangeFilter(max_range=1, origin_key="nudge_unit")],
)
MoveUnitStep(
    unit_key="nudge_unit",
    destination_key="nudge_dest",
    range_val=1,
    is_movement_action=False,  # NOT a movement action
)
```

**Set Context Flag**:
```python
SetContextFlagStep(key="auto_block", value=True)
SetContextFlagStep(key="defense_invalid", value=True)
SetContextFlagStep(key="ignore_minion_defense", value=True)
```

## Step Library

### Atomic Actions
| Step Class | Purpose | Key Parameters |
| :--- | :--- | :--- |
| `MoveUnitStep` | Move unit (pathfinding) | `unit_id`, `destination_key`, `range_val`, `is_movement_action` |
| `PlaceUnitStep` | Teleport unit | `unit_id`, `destination_key`, `target_hex_arg` |
| `PushUnitStep` | Push unit away | `target_key`, `distance`, `collision_output_key`, `distance_key` |
| `SwapUnitsStep` | Swap positions | `unit_a_id`, `unit_b_key` |
| `DefeatUnitStep` | Defeat a unit | `victim_id` |
| `RemoveUnitStep` | Remove from board | `unit_id`, `return_to_zone` |
| `DiscardCardStep` | Discard specific card | `card_id`, `card_key`, `hero_id`, `hero_key` |
| `RetrieveCardStep` | Retrieve card from discard to hand | `card_key`, `active_if_key` |
| `MoveSequenceStep` | Full movement action flow | `unit_id`, `range_val`, `force_straight_line`, `force_full_distance` |
| `ForceDefenseCardMovementStep` | Force defender to use movement card | `target_key`, `force_straight_line`, `force_full_distance` |

### Combat
| Step Class | Purpose | Key Parameters |
| :--- | :--- | :--- |
| `AttackSequenceStep` | Full combat flow | `damage`, `range_val`, `target_id_key`, `target_filters` |
| `ReactionWindowStep` | Request defense | `target_player_key` |
| `ResolveDefenseTextStep` | Resolve defense effects | - |
| `ResolveCombatStep` | Resolve damage/defense | - |

### Selection
| Step Class | Purpose | Key Parameters |
| :--- | :--- | :--- |
| `SelectStep` | Generic selector | `target_type`, `filters`, `output_key`, `prompt`, `is_mandatory` |
| `MultiSelectStep` | Select multiple | `max_selections`, `min_selections`, `output_key` |

### Control Flow
| Step Class | Purpose | Key Parameters |
| :--- | :--- | :--- |
| `MayRepeatOnceStep` | Repeat once | `steps_template`, `prompt`, `active_if_key` |
| `MayRepeatNTimesStep` | Repeat N times | `steps_template`, `max_repeats`, `prompt` |
| `ForEachStep` | Iterate over list | `list_key`, `item_key`, `steps_template` |
| `CheckAdjacencyStep` | Check adjacency | `unit_a_id`, `unit_b_key`, `output_key` |
| `CheckUnitTypeStep` | Check HERO/MINION | `unit_key`, `expected_type`, `output_key` |
| `CombineBooleanContextStep` | Combine flags | `key_a`, `key_b`, `output_key`, `operation` |
| `CountStep` | Count entities matching filters | `target_type`, `filters`, `output_key` |
| `CollectUnitsStep` | Collect **all** matching units into a list (no prompt) | `target_type`, `filters`, `output_key` |
| `CheckContextConditionStep` | Evaluate context value vs threshold | `input_key`, `operator`, `threshold`, `output_key` |

> **"each X" / "all X" (mandatory, no choice)** → `CollectUnitsStep` (gathers every
> match, respecting immunity unless `skip_immunity_filter=True`) → `ForEachStep`.
> Do **not** use `MultiSelectStep` for "each" — that implies the actor picks which.

### Effects & Modifiers
| Step Class | Purpose | Key Parameters |
| :--- | :--- | :--- |
| `CreateEffectStep` | Create zone/aura | `effect_type`, `scope`, `duration`, `restrictions` |
| `CreateModifierStep` | Apply stat modifier | `target_key`, `stat_type`, `value_mod`, `duration` |
| `PlaceMarkerStep` | Place marker | `marker_type`, `target_key`, `value` |
| `RemoveMarkerStep` | Remove marker | `marker_type` |

### Utility
| Step Class | Purpose | Key Parameters |
| :--- | :--- | :--- |
| `SetContextFlagStep` | Set flag in context | `key`, `value` |
| `SetActorStep` | Change current actor | `actor_id`, `actor_key`, `save_key` |
| `LogMessageStep` | Debug print | `message` |

## Filter Library

### Targeting Filters
| Filter Class | Purpose |
| :--- | :--- |
| `RangeFilter(max_range=N)` | Within N hexes |
| `RangeFilter(max_range=N, min_range=M)` | Between M and N hexes |
| `TeamFilter(relation="ENEMY")` | "FRIENDLY", "ENEMY", "SELF" |
| `UnitTypeFilter(unit_type="HERO")` | "HERO", "MINION" |
| `ImmunityFilter()` | **Always include** for offensive actions |

### Position Filters
| Filter Class | Purpose |
| :--- | :--- |
| `AdjacencyFilter` | Must be adjacent to X |
| `AdjacencyToContextFilter(target_key="id")` | Adjacent to unit in context |
| `ObstacleFilter(is_obstacle=False)` | Hex must not be obstacle — **also excludes occupied hexes** (`tile.is_obstacle = is_terrain or is_occupied`), so this is the "empty space" filter. There is no `OccupiedFilter`. |
| `MovementPathFilter(range_val=N, unit_id=X)` | Valid movement path |
| `TerrainFilter(terrain_type="WATER")` | Specific terrain |
| `BattleZoneFilter()` | Hex must be in active battle zone |

### Advanced Filters
| Filter Class | Purpose |
| :--- | :--- |
| `NotInStraightLineFilter()` | "Not in a straight line" |
| `LineBehindTargetFilter(target_key="id", length=3)` | Behind target (straight line) |
| `ExcludeIdentityFilter(exclude_keys=["id"])` | Cannot select unit in context |
| `HasEmptyNeighborFilter()` | Must have empty neighbor hex |
| `ForcedMovementByEnemyFilter()` | Can be moved by enemy |
| `CanBePlacedByActorFilter()` | Can be placed by actor |
| `FastTravelDestinationFilter(unit_id=X)` | Valid fast travel destination |
| `RelativeDistanceFilter(reference_key="id", operator=">")` | Distance from origin vs reference unit (`>`, `>=`, `==`, `<=`, `<`) |
| `SpawnPointFilter(has_spawn_point=False)` | Not on spawn point |
| `AdjacentSpawnPointFilter(is_empty=True, must_not_have=True)` | Not adjacent to empty spawn |
| `AdjacentSpawnPointFilter(..., battle_zone_only=True)` | Only considers spawn points in active battle zone |
| `UnitOnSpawnPointFilter()` | Unit occupies hex with spawn point |
| `CardsInContainerFilter(container, min_cards, max_cards)` | Hero has N cards in container |
| `OrFilter(filters=[...])` | Passes if ANY child filter passes |
| `AndFilter(filters=[...])` | Passes if ALL child filters pass |
| `CountMatchFilter(sub_filters=[...], min_count=N, include_tokens=False)` | Candidate (hex or unit-id) passes if N+ entities match `sub_filters` measured from it. The "is this near N things matching X?" filter. |

**"a unit adjacent to a [token/unit]" — use `CountMatchFilter`, not a bespoke filter:**
```python
# Target an enemy unit that is adjacent to a Tree token:
SelectStep(
    target_type=TargetType.UNIT,
    filters=[
        TeamFilter(relation="ENEMY"),
        RangeFilter(max_range=stats.range),
        CountMatchFilter(
            include_tokens=True,   # needed to count tokens, not just units
            min_count=1,
            sub_filters=[
                TokenTypeFilter(token_type=TokenType.TREE),
                # measure adjacency FROM the candidate, via the published origin key:
                RangeFilter(max_range=1, origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY),
            ],
        ),
    ],
)
```
The candidate's hex is published to `CountMatchFilter.ORIGIN_HEX_KEY`; sub-filters that
accept `origin_hex_key` (e.g. `RangeFilter`) then measure distance from the candidate.

## TargetType Enum

Use these values for `SelectStep.target_type`:
- `TargetType.UNIT` - Select a unit
- `TargetType.UNIT_OR_TOKEN` - Select unit or token
- `TargetType.HEX` - Select a hex coordinate
- `TargetType.CARD` - Select a card from hand/discard/played
- `TargetType.NUMBER` - Select from `number_options`

## SelectStep Features

### Target Types
```python
# Units (heroes + minions)
SelectStep(target_type=TargetType.UNIT, ...)

# Units and tokens
SelectStep(target_type=TargetType.UNIT_OR_TOKEN, ...)

# Hex coordinates
SelectStep(target_type=TargetType.HEX, ...)

# Cards
SelectStep(target_type=TargetType.CARD, ...)

# Number selection
SelectStep(target_type=TargetType.NUMBER, number_options=[1, 2, 3], ...)
```

### Card Selection
```python
SelectStep(
    target_type=TargetType.CARD,
    card_container=CardContainerType.HAND,  # HAND, PLAYED, DISCARD, DECK
    context_hero_id_key="victim_id",  # Whose hand?
    override_player_id_key="victim_id",  # Who chooses?
    prompt="Select card to discard",
)
```

### Optional Selections
```python
SelectStep(
    is_mandatory=False,  # "you may"
    filters=[...],
)
```

### Auto-Select if Only One Option
```python
SelectStep(
    auto_select_if_one=True,  # Don't prompt if trivial
    filters=[...],
)
```

### Skip Immunity Filter
```python
SelectStep(
    skip_immunity_filter=True,  # For non-offensive selections
    target_type=TargetType.UNIT,
    filters=[TeamFilter(relation="FRIENDLY")],
)
```

## Context Key Patterns

### AttackSequenceStep
- `target_id_key`: Stores selected target ID in context
- If omitted, uses internal selection

### PushUnitStep
- `target_key`: Read unit ID from context
- `distance`: Literal distance
- `distance_key`: Read distance from context (variable push)
- `collision_output_key`: Stores `True` if collision occurred

### MoveUnitStep
- `unit_id` / `unit_key`: Who to move
- `destination_key`: Read hex from context
- `range_val`: Max movement distance

### SelectStep
- `output_key`: Where to store selection
- `active_if_key`: Only run if context key exists and truthy

### Defense Context
- `attack_is_ranged`: True if incoming attack is ranged
- `attacker_id`: ID of attacking unit
- `defender_id`: ID of defending hero

## Stat Types

Use with `CreateModifierStep` or `stats.primary_value`:
- `StatType.ATTACK` - Attack damage
- `StatType.DEFENSE` - Defense value
- `StatType.MOVEMENT` - Movement points
- `StatType.RANGE` - Attack/skill range
- `StatType.RADIUS` - Area of effect size
- `StatType.INITIATIVE` - Card initiative

## Duration Types

Use with `CreateModifierStep` / `CreateEffectStep` (these are the only members — there is
no `PERMANENT`):
- `DurationType.THIS_TURN` - Lasts until end of current turn
- `DurationType.NEXT_TURN` - Activates next turn, expires at end of that turn
- `DurationType.THIS_ROUND` - Lasts until end of current round
- `DurationType.PASSIVE` - Permanent until the source is removed (card leaves play / token removed)

### Effect Lifecycle Gotcha: end-of-round ordering

`EndPhaseStep` expires `THIS_ROUND` effects — **and fires their `finishing_steps`** —
**before** `MinionBattleStep`. Choose the representation by what the card text needs:

- **"End of round: [do an action]"** (e.g. *Final Embrace*: "Defeat an enemy minion
  adjacent to you") → `THIS_ROUND` effect carrying `finishing_steps`. It fires *before* the
  battle, so the defeat correctly changes the minion count. This is what you want.
- **"This round: [passive rule read DURING the battle]"** (e.g. *Claim/Assert Dominance*:
  "enemy minions adjacent to you do not count toward the minion total") → use
  **`DurationType.PASSIVE`**, card-bound. A `THIS_ROUND` effect would already be expired by
  the time `MinionBattleStep` runs, making it a silent no-op. `PASSIVE` survives into the
  battle and is cleaned up when the card is retrieved in `EndPhaseCleanupStep` (after the
  battle) — a one-round lifetime that covers the battle.

This bug is invisible to isolated unit tests (which call `_resolve_minion_battle` directly);
only an end-to-end test through the real `EndPhaseStep` catches it.

## Passive Triggers

Use with `get_passive_config()`:
- `PassiveTrigger.BEFORE_ATTACK` - Before performing Attack action
- `PassiveTrigger.BEFORE_MOVEMENT` - Before moving
- `PassiveTrigger.BEFORE_SKILL` - Before performing Skill action
- `PassiveTrigger.AFTER_ATTACK` - After an attack resolves
- `PassiveTrigger.AFTER_BASIC_ACTION` - After a basic card action
- `PassiveTrigger.AFTER_BASIC_SKILL` - After Gold/Silver basic SKILL
- `PassiveTrigger.AFTER_PUSH` - After a push resolves
- `PassiveTrigger.AFTER_PLACE_MARKER` - After a marker is placed
- `PassiveTrigger.AFTER_CARD_DISCARD` - After *any* card discard (fires on every discard; use `should_offer_passive` to filter by `context["discard_source"]` HAND/PLAYED or `context["discarded_card_owner_id"]`)
- (Check `domain/models/enums.py` for the current source of truth)

## Real-World Examples

### Example 1: Wasp - Kinetic Repulse
```python
@register_effect("kinetic_repulse")
class KineticRepulseEffect(CardEffect):
    """
    "Push up to 2 enemy units adjacent to you 3 spaces;
    if a pushed hero is stopped by an obstacle, that hero discards a card."
    """

    def build_steps(self, state, hero, card, stats):
        return [
            # 1. Select up to 2 adjacent enemies
            MultiSelectStep(
                target_type=TargetType.UNIT,
                prompt="Select up to 2 adjacent enemies to push",
                output_key="push_targets",
                max_selections=2,
                min_selections=0,
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            # 2. For each: push, check collision, check if hero, discard
            ForEachStep(
                list_key="push_targets",
                item_key="current_target",
                steps_template=[
                    PushUnitStep(
                        target_key="current_target",
                        distance=3,
                        collision_output_key="collision",
                    ),
                    CheckUnitTypeStep(
                        unit_key="current_target",
                        expected_type="HERO",
                        output_key="is_hero",
                    ),
                    CombineBooleanContextStep(
                        key_a="collision",
                        key_b="is_hero",
                        output_key="should_discard",
                        operation="AND",
                    ),
                    ForceDiscardStep(
                        victim_key="current_target",
                        active_if_key="should_discard",
                    ),
                ],
            ),
        ]
```

### Example 2: Arien - Violent Torrent
```python
@register_effect("violent_torrent")
class ViolentTorrentEffect(CardEffect):
    """
    "Target a unit adjacent to you. Before the attack: Up to 1 enemy hero
    in any of the 5 spaces in a straight line directly behind the target
    discards a card, or is defeated. May repeat once on a different unit."
    """

    def build_steps(self, state, hero, card, stats):
        attack_steps = [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select target",
                output_key="victim_id_1",
                filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero behind target (optional)",
                output_key="backstab_victim_1",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    LineBehindTargetFilter(target_key="victim_id_1", length=5),
                ],
            ),
            ForceDiscardOrDefeatStep(victim_key="backstab_victim_1"),
            AttackSequenceStep(damage=stats.primary_value, target_id_key="victim_id_1", range_val=1),
        ]

        repeat_template = [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select second target (optional)",
                output_key="victim_id_2",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                    ExcludeIdentityFilter(exclude_keys=["victim_id_1"]),
                ],
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy hero behind second target (optional)",
                output_key="backstab_victim_2",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    LineBehindTargetFilter(target_key="victim_id_2", length=5),
                ],
            ),
            ForceDiscardOrDefeatStep(victim_key="backstab_victim_2"),
            AttackSequenceStep(damage=stats.primary_value, target_id_key="victim_id_2", range_val=1),
        ]

        return attack_steps + [MayRepeatOnceStep(steps_template=repeat_template)]
```

### Example 3: Wasp - Stop Projectiles (Defense)
```python
@register_effect("stop_projectiles")
class StopProjectilesEffect(CardEffect):
    """Block a ranged attack."""

    def build_defense_steps(self, state, defender, card, stats, context):
        if context.get("attack_is_ranged"):
            return [SetContextFlagStep(key="auto_block", value=True)]
        return [SetContextFlagStep(key="defense_invalid", value=True)]
```

### Example 4: Arien - Living Tsunami (Passive)
```python
@register_effect("living_tsunami")
class LivingTsunamiEffect(CardEffect):
    """Once per turn, before performing an Attack action, you may move 1 space."""

    def get_passive_config(self):
        return PassiveConfig(
            trigger=PassiveTrigger.BEFORE_ATTACK,
            uses_per_turn=1,
            is_optional=True,
            prompt="Living Tsunami: Move 1 space before attacking?",
        )

    def get_passive_steps(self, state, hero, card, trigger, context):
        if trigger != PassiveTrigger.BEFORE_ATTACK:
            return []
        return [MoveSequenceStep(unit_id=hero.id, range_val=1, is_mandatory=False)]
```

### Example 4b: Garrus - Battle Fury (Broad Trigger + should_offer_passive)
```python
@register_effect("battle_fury")
class BattleFuryEffect(CardEffect):
    """Ultimate passive: when one of YOUR played cards is discarded,
    you may perform its primary action.

    AFTER_CARD_DISCARD fires on every discard in the game — from hand,
    from played, by any player. We only care about Garrus's own played
    cards, so we gate with should_offer_passive to avoid prompting YES/NO
    on unrelated discards."""

    def get_passive_config(self):
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_CARD_DISCARD,
            uses_per_turn=0,  # unlimited
            is_optional=True,
            prompt="Battle Fury: Perform the discarded card's primary action?",
        )

    def should_offer_passive(self, state, hero, card, trigger, context):
        # Only fire for discards from the played area...
        if context.get("discard_source") != CardContainerType.PLAYED.value:
            return False
        # ...and only when it was Garrus's own card.
        if context.get("discarded_card_owner_id") != str(hero.id):
            return False
        return True

    def get_passive_steps(self, state, hero, card, trigger, context):
        discarded_id = context.get("discarded_card_id")
        discarded = next(
            (c for c in hero.discard_pile if c.id == discarded_id), None
        )
        if not discarded:
            return []
        # Delegate to the discarded card's own effect / stats.
        primary = discarded.primary_action
        if primary in (ActionType.SKILL, ActionType.ATTACK) and discarded.effect_id:
            effect = CardEffectRegistry.get(discarded.effect_id)
            if effect:
                return effect.get_steps(state, hero, discarded)
        stats = compute_card_stats(state, hero.id, discarded)
        if primary == ActionType.ATTACK:
            return [AttackSequenceStep(damage=stats.primary_value, range_val=stats.range or 1)]
        if primary == ActionType.MOVEMENT:
            return [MoveSequenceStep(unit_id=hero.id, range_val=stats.primary_value)]
        return []
```

### Example 5: Xargatha - Devoted Followers (Conditional Card Retrieval)
```python
@register_effect("devoted_followers")
class DevotedFollowersEffect(CardEffect):
    """
    "If you are adjacent to an enemy unit, you may retrieve a discarded card."
    """

    def build_steps(self, state, hero, card, stats):
        return [
            # 1. Count adjacent enemies (reuses SelectStep's filter system)
            CountStep(
                target_type=TargetType.UNIT,
                filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
                output_key="adjacent_enemy_count",
            ),
            # 2. Check if count >= 1 (stores True or None for active_if_key)
            CheckContextConditionStep(
                input_key="adjacent_enemy_count",
                operator=">=", threshold=1,
                output_key="has_adjacent_enemy",
            ),
            # 3. Select card from discard (only if condition met)
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="Select a discarded card to retrieve",
                output_key="retrieved_card",
                is_mandatory=False,
                active_if_key="has_adjacent_enemy",
            ),
            # 4. Move card from discard to hand
            RetrieveCardStep(
                card_key="retrieved_card",
                active_if_key="retrieved_card",
            ),
        ]
```

## Inheritance Patterns

Multiple effects can share logic by inheriting:
```python
@register_effect("lift_up")
class LiftUpEffect(CardEffect):
    def build_steps(self, state, hero, card, stats):
        orbit_steps = [...]
        return steps + orbit_steps + [MayRepeatOnceStep(steps_template=orbit_steps)]

@register_effect("control_gravity")
class ControlGravityEffect(LiftUpEffect):
    """Same as Lift Up but uses card stats (Radius 3)."""
    pass  # Inherits all logic

@register_effect("center_of_mass")
class CenterOfMassEffect(LiftUpEffect):
    """Same but repeats TWICE."""
    def build_steps(self, state, hero, card, stats):
        orbit_steps = [...]
        return steps + orbit_steps + [
            MayRepeatNTimesStep(max_repeats=2, steps_template=orbit_steps)
        ]
```

## Testing Strategy

Create integration tests in `tests/engine/test_[hero]_[card].py`.

1.  **Setup**: Use `GameState` fixture, place Hero and dummy enemies.
2.  **Trigger**: Push `ResolveCardStep(hero_id=...)`.
3.  **Drive**: Call `process_resolution_stack(state)` repeatedly.
4.  **Input**: Inspect `state.execution_stack[-1].pending_input` and provide mock input.
5.  **Verify**: Assert final positions in `state.entity_locations` or checks on `state.active_modifiers`.

## Source of Truth

The codebase is the ultimate authority. Check these files for the latest definitions:

| Component | File Path | What to look for |
| :--- | :--- | :--- |
| **Available Steps** | `src/goa2/engine/steps.py` | Classes inheriting from `GameStep` |
| **Available Filters** | `src/goa2/engine/filters.py` | Classes inheriting from `FilterCondition` |
| **Status Tags** | `src/goa2/engine/validation.py` | `prevention_tags` dict |
| **Effect/Action Types** | `src/goa2/domain/models/enums.py` | `EffectType`, `ActionType`, `StatType`, `PassiveTrigger`, `TargetType` |
| **Effect Definitions** | `src/goa2/domain/models/effect.py` | `ActiveEffect` model and `EffectType` definitions |
| **CardEffect Base** | `src/goa2/engine/effects.py` | `CardEffect`, `PassiveConfig` |

## Common Pitfalls

- **Using `get_steps()` instead of `build_steps()`** - Method name is `build_steps()`
- **Forgetting `stats` parameter** - Stats are pre-computed and passed as 4th argument
- **Not handling `None` return in defense** - `build_defense_steps()` returns `Optional[List[GameStep]]`, return `None` to fall back
- **Forgetting `ImmunityFilter`** - Always include for offensive unit targeting (unless `skip_immunity_filter=True`)
- **Missing `Context` patterns** - Defense context has `attack_is_ranged`, `attacker_id` etc.
- **Not using `TargetType` enum** - Don't use strings like `"UNIT"`, use `TargetType.UNIT`
- **Forgetting `active_if_key`** - Use this for conditional execution ("if adjacent", "you may")
- **Not emitting events** - Steps that change observable state must emit `GameEvent`s
