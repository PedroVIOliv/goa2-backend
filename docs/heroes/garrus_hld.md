# Garrus: High-Level Design

## Overview

Garrus is a melee tank/bruiser themed around battlefield control, displacement, and discard-based empowerment. His kit revolves around:
- **Red line**: Conditional charge attacks (move-then-attack if cards in discard) and post-attack displacement (dash to enemy + push)
- **Blue line**: Pulling friendlies closer / pushing enemies farther (with repeats at higher tiers)
- **Green line**: Conditional card retrieval (requires 2+ enemies in radius) and ranged forced discard
- **Silver**: Area movement restriction + voluntary self-discard
- **Gold**: Attack with scaling bonus from discard pile
- **Ultimate**: Triggered passive — perform primary action of resolved cards when they are discarded

---

## Card Family Analysis

### Family 1: Chase Line (Trace / Chase / Hunt Down) — RED

**Cards:**
| Card | Tier | Move | Target |
|------|------|------|--------|
| Trace | I | 1 space (may) | Hero adj. |
| Chase | II | 2 spaces | Hero adj. |
| Hunt Down | III | 3 spaces | Hero adj. |

**Effect text pattern:** "Choose one — Before the attack: If you have one or more cards in the discard, move up to N spaces. Target a hero adjacent to you. / Target a unit adjacent to you."

**Implementation:**
1. Branch choice via `SelectStep(target_type=NUMBER)` with `number_options=[0, 1]` and `number_labels={0: "Standard attack", 1: "Charge (move then attack hero)"}` — stores the choice in context.
2. If Charge (1) chosen:
   - Condition check: `CountCardsStep` on discard pile → `CheckContextConditionStep` (>= 1)
   - If met: `MoveUnitStep` (up to N spaces, `is_mandatory=False`, gated by `active_if_key`)
   - `AttackSequenceStep` targeting adjacent hero only (`UnitTypeFilter(HERO)`), gated by `active_if_key`
3. If Standard (0) chosen:
   - `AttackSequenceStep` targeting adjacent unit (hero or minion), gated by `active_if_key`

**Note:** Use `SELECT_NUMBER` input style (not `CHOOSE_ACTION`). This matches the established branching convention used elsewhere in the codebase (e.g., Brogan's push-distance prompts).

**Difficulty: EASY** — All building blocks exist: `CountCardsStep`, `CheckContextConditionStep`, `MoveUnitStep`, `AttackSequenceStep`, `SelectStep` with `CHOOSE_ACTION`. This is a standard branching pattern already used in other heroes (e.g., Whisper's branching effects).

**Existing steps/filters needed:** `CountCardsStep`, `CheckContextConditionStep`, `MoveUnitStep`, `AttackSequenceStep`, `SelectStep`, `UnitTypeFilter`, `TeamFilter`, `RangeFilter`
**New steps/filters needed:** None
**Engine changes needed:** None

---

### Family 2: Push Line (Blunt Force / Send Flying) — RED

**Cards:**
| Card | Tier | Self-Move | Push |
|------|------|-----------|------|
| Blunt Force | II | 1 space | 3 spaces |
| Send Flying | III | 2 spaces | 3 spaces |

**Effect text:** "Target a unit adjacent to you. After the attack: You may move up to N spaces to a space adjacent to an enemy hero; if you do, push that hero 3 spaces, ignoring obstacles."

**Implementation:**
1. `AttackSequenceStep` targeting adjacent unit
2. After attack: Select hex to move to (filtered: within N range, adjacent to an enemy hero)
   - `SelectStep(target_type=HEX)` with `RangeFilter(max_range=N)`, `AdjacencyFilter(target_tags=["ENEMY", "HERO"])`, `ObstacleFilter`
   - This step is optional (`is_mandatory=False`)
3. `MoveUnitStep` to selected hex
4. Record which enemy hero the actor is now adjacent to (or use context from the AdjacencyFilter match)
5. `PushUnitStep` targeting that enemy hero, distance=3, **ignoring obstacles**

**Key challenge:** "Ignoring obstacles" on push. The current `PushUnitStep` checks obstacles during push and stops early. It does NOT have an `ignore_obstacles` flag. Two subtleties:
1. **Cannot end on an obstacle.** Even when ignoring obstacles mid-path, the final resting hex must be a legal space. Treat obstacles the same way mines/passable tokens are already handled: the pushed unit may traverse them, but if the path would terminate on one, we need to either stop one hex short (last legal hex before the obstacle) or slide through until a legal hex is found. The existing `is_passable_token` logic in `PushUnitStep.resolve()` (line ~3136) is the precedent — it already lets a push cross passable tokens; we extend that model to *all* obstacles when `ignore_obstacles=True`, and ensure the final hex is validated.
2. **Mines/triggers still fire on traversal.** When an enemy hero is pushed across a mine or trigger-style token, the mine must still trigger even though the push "ignores" it for pathing purposes. The engine already handles mine triggers through `MoveUnitStep` / movement hooks; since `PushUnitStep` calls into the same displacement pipeline for each hex stepped, passing through an obstacle should still emit the movement events that drive mine triggers. This needs to be verified in the implementation — `ignore_obstacles` must only disable the *pathing block*, not the *traversal side-effects*.

**Difficulty: MEDIUM** — The attack + conditional move + push flow is straightforward with existing steps. However:
- **Need to add `ignore_obstacles: bool = False` to `PushUnitStep`.** When True:
  - Obstacle hexes do not terminate the push (like passable tokens today).
  - The final landing hex must still be a legal occupiable hex — if the path would stop on an obstacle, stop on the last legal hex before it (or continue past it, per rules). This needs a post-path "land validation" pass.
  - Mine/trigger side-effects on traversed hexes must still fire (pushed units are still considered to have entered those hexes).
- Need to determine which enemy hero to push after the self-move. If only one enemy hero is adjacent after moving, auto-select. If multiple, need a `SelectStep` to choose. An `AdjacencyToContextFilter` or recording the "adjacent enemy" during hex selection can handle this.
- The hex selection filter "space adjacent to an enemy hero" already exists as `AdjacencyFilter(target_tags=["ENEMY", "HERO"])`.

**Existing steps/filters needed:** `AttackSequenceStep`, `SelectStep`, `MoveUnitStep`, `PushUnitStep`, `RangeFilter`, `AdjacencyFilter`, `ObstacleFilter`, `TeamFilter`
**New steps/filters needed:** None
**Engine changes needed:**
- Add `ignore_obstacles: bool = False` to `PushUnitStep`:
  - When True, obstacle hexes do not terminate the push path (mirror current passable-token logic).
  - Must validate that the final landing hex is legal (no ending on an obstacle — slide back to the last legal hex if needed).
  - Must preserve traversal side-effects (mines/triggers on crossed hexes still fire — enemy heroes pushed over mines still set them off).

---

### Family 3: Pull Friendlies (Form Up! / Testudo!) — BLUE

**Cards:**
| Card | Tier | Range | Repeats |
|------|------|-------|---------|
| Form Up! | II | 3 | Once (total 2 moves) |
| Testudo! | III | 3 | Twice (total 3 moves) |

**Effect text:** "Move a friendly unit in range 1 space to a space closer to you. May repeat [once / up to two times]."

**Implementation:**
1. Base action:
   - `SelectStep(target_type=UNIT)` — select friendly unit in range (`TeamFilter(FRIENDLY)`, `RangeFilter(max_range=3)`)
   - `SelectStep(target_type=HEX)` — select destination hex (1 space from target, closer to Garrus: `RelativeDistanceFilter(operator="<")`, `ObstacleFilter`)
   - `MoveUnitStep` to move the selected unit
2. Wrap in `MayRepeatNTimesStep(max_repeats=1)` for Form Up! or `MayRepeatNTimesStep(max_repeats=2)` for Testudo!

**Note:** "Closer to you" maps to `RelativeDistanceFilter(operator="<", reference_key="selected_unit_hex", origin_id=hero.id)` — candidate hex distance to Garrus must be less than current distance. This filter already exists and was generalized for Misa.

**Difficulty: EASY** — `MayRepeatNTimesStep` already exists and handles the repeat prompt. `RelativeDistanceFilter` with `operator="<"` handles "closer to you". The select-unit-then-select-hex-then-move pattern is standard. Need to ensure the moved unit's new position is tracked for subsequent repeats (which it is, since `entity_locations` is updated by `MoveUnitStep`).

**Existing steps/filters needed:** `SelectStep`, `MoveUnitStep`, `MayRepeatNTimesStep`, `RangeFilter`, `TeamFilter`, `RelativeDistanceFilter`, `ObstacleFilter`
**New steps/filters needed:** None
**Engine changes needed:** None

---

### Family 4: Push Enemies (Menace / Threaten / Terrify) — BLUE

**Cards:**
| Card | Tier | Range | Repeats |
|------|------|-------|---------|
| Menace | I | 2 | None |
| Threaten | II | 2 | Once |
| Terrify | III | 2 | Twice |

**Effect text:** "Move an enemy unit in range 1 space to a space farther away from you. [May repeat once / May repeat up to two times.]"

**Implementation:**
1. Base action:
   - `SelectStep(target_type=UNIT)` — select enemy unit in range (`TeamFilter(ENEMY)`, `RangeFilter(max_range=2)`)
   - `SelectStep(target_type=HEX)` — select destination hex (1 space from target, farther from Garrus: `RelativeDistanceFilter(operator=">")`, `ObstacleFilter`)
   - `MoveUnitStep` to move the enemy unit (this is forced movement, not the enemy's own movement action)
2. Menace: no repeat. Threaten: `MayRepeatNTimesStep(max_repeats=1)`. Terrify: `MayRepeatNTimesStep(max_repeats=2)`.

**Note:** This is forced movement by Garrus, so it should use `ForcedMovementByEnemyFilter` or similar to bypass immunity to self-movement. Need to verify the forced movement semantics — the enemy doesn't choose, Garrus does.

**Difficulty: EASY** — Mirror of Family 3 with `RelativeDistanceFilter(operator=">")` for "farther away". Same repeat pattern.

**Existing steps/filters needed:** `SelectStep`, `MoveUnitStep`, `MayRepeatNTimesStep`, `RangeFilter`, `TeamFilter`, `RelativeDistanceFilter`, `ObstacleFilter`
**New steps/filters needed:** None
**Engine changes needed:** None

---

### Family 5: Conditional Retrieval (Hold Ground / Make a Stand / Battle Ready) — GREEN

**Cards:**
| Card | Tier | Radius | Retrieve |
|------|------|--------|----------|
| Hold Ground | I | 3 | 1 card |
| Make a Stand | II | 4 | 1 card |
| Battle Ready | III | 4 | Up to 2 cards |

**Effect text:** "If there are at least two enemy heroes in radius, you may retrieve [a discarded card / up to two discarded cards]."

**Implementation:**
1. `CountStep(target_type=UNIT)` with `TeamFilter(ENEMY)`, `UnitTypeFilter(HERO)`, `RangeFilter(max_range=radius)` → `output_key="enemy_count"`
2. `CheckContextConditionStep(input_key="enemy_count", operator=">=", threshold=2, output_key="can_retrieve")`
3. For T1/T2 (retrieve 1):
   - `SelectStep(target_type=CARD)` from discard → `RetrieveCardStep` (with `active_if_key="can_retrieve"`, `is_mandatory=False`)
4. For T3 (retrieve up to 2):
   - Same as above but repeat: two sequential select+retrieve pairs, both optional

**Note:** `CountStep` uses the filter system to count enemy heroes in radius. The "radius" on these cards is the card's `radius_value` attribute. For T3, the "up to two" means two optional retrieve operations — not a `MayRepeatNTimesStep` since each retrieval picks from a shrinking pool.

**Difficulty: EASY** — All steps exist. `CountStep` + `CheckContextConditionStep` is the standard condition pattern. `SelectStep` for cards + `RetrieveCardStep` is standard.

**Existing steps/filters needed:** `CountStep`, `CheckContextConditionStep`, `SelectStep`, `RetrieveCardStep`, `TeamFilter`, `UnitTypeFilter`, `RangeFilter`
**New steps/filters needed:** None
**Engine changes needed:** None

---

### Family 6: Forced Discard (Light Pilum / Heavy Pilum) — GREEN

**Cards:**
| Card | Tier | Range | Discard | Defeat | Self-Move |
|------|------|-------|---------|--------|-----------|
| Light Pilum | II | 2 | Yes (if able) | No | 1 space |
| Heavy Pilum | III | 2 | Yes | Or defeated | 2 spaces |

**Light Pilum:** "An enemy hero in range discards a card, if able. You may move 1 space."
**Heavy Pilum:** "An enemy hero in range discards a card, or is defeated. You may move up to 2 spaces."

**Implementation:**

*Light Pilum:*
1. `SelectStep(target_type=UNIT)` — enemy hero in range 2 (`TeamFilter(ENEMY)`, `UnitTypeFilter(HERO)`, `RangeFilter(max_range=2)`)
2. `ForceDiscardStep(victim_key="target_id")` — forces discard if they have cards, otherwise no penalty
3. `MoveUnitStep(range_val=1, is_mandatory=False)` — optional self-move

*Heavy Pilum:*
1. `SelectStep(target_type=UNIT)` — enemy hero in range 2
2. `ForceDiscardOrDefeatStep(victim_key="target_id")` — forces discard, or defeats if no cards
3. `MoveUnitStep(range_val=2, is_mandatory=False)` — optional self-move

**Difficulty: EASY** — `ForceDiscardStep` and `ForceDiscardOrDefeatStep` already exist and handle the "discard or defeat" pattern. Standard select + force-discard + optional move flow.

**Existing steps/filters needed:** `SelectStep`, `ForceDiscardStep`, `ForceDiscardOrDefeatStep`, `MoveUnitStep`, `TeamFilter`, `UnitTypeFilter`, `RangeFilter`
**New steps/filters needed:** None
**Engine changes needed:** None

---

### Angry Strike — GOLD

**Effect text:** "Target a unit adjacent to you; +1 Attack for every card in your discard."

**Implementation:**
1. `CountCardsStep(card_container=DISCARD, output_key="discard_count")`
2. Attack with bonus: `AttackSequenceStep` with `bonus_key="discard_count"` to add the discard count to attack value

**Key question:** How does attack bonus work? The `AttackSequenceStep` needs to receive a dynamic bonus. Looking at existing patterns, `stats.primary_value` is computed at card resolution time and can include modifier bonuses. However, the discard count changes dynamically — it depends on game state at resolution time, not card stats.

**Options:**
- a) Compute the bonus in the effect's `build_steps()` using `len(hero.discard_pile)` at effect build time and pass it as a static attack value. This works because `build_steps()` is called at resolution time when the discard pile is already determined.
- b) Use `CountCardsStep` + context passing to dynamically set the attack bonus.

Option (a) is simpler and correct — `build_steps()` runs at the moment the card resolves, so `len(hero.discard_pile)` reflects the current state.

**Difficulty: EASY** — The primary action value is 4. We compute `4 + len(hero.discard_pile)` in `build_steps()` and pass it to `AttackSequenceStep`. No new steps needed. Precedent: other heroes compute dynamic values in `build_steps()`.

**Existing steps/filters needed:** `AttackSequenceStep`, `SelectStep`, `RangeFilter`, `TeamFilter`
**New steps/filters needed:** None
**Engine changes needed:** None

---

### Chilling Howl — SILVER

**Effect text:** "You may discard one of your resolved cards. This round: Enemy heroes in radius cannot fast travel, or move more than 2 spaces with a movement action."

**Implementation:**
1. Optional self-discard: Select from resolved cards (`SelectStep(target_type=CARD)`, `is_mandatory=False`, filtered to resolved cards) → `DiscardCardStep`
2. Create movement restriction effect: `CreateEffectStep` with:
   - `effect_type=EffectType.MOVEMENT_ZONE`
   - `scope=EffectScope(shape=Shape.RADIUS, range=radius, origin_id=hero.id, affects=AffectsFilter.ENEMY_HEROES)`
   - `duration=DurationType.THIS_ROUND` (not THIS_TURN — card says "this round")
   - `max_value=2` (movement cap at 2 spaces)
   - `limit_actions_only=True`
   - `restrictions=[ActionType.FAST_TRAVEL]`

**Note:** This is almost identical to Arien's Deluge effect, except:
- Arien's is "this turn" with `max_value=1`; Garrus's is "this round" with `max_value=2`
- Garrus adds optional self-discard before the effect
- The movement restriction applies for the whole round, not just Garrus's turn

**Note on "resolved cards":** Per game rules, a "resolved card" is any card in `hero.played_cards` — being in `played_cards` is sufficient (cards there are already marked `CardState.RESOLVED` by the engine). So the filter is simply "select a card from `played_cards`."

**Difficulty: EASY** — The movement restriction pattern is already established (Arien's Deluge). `DurationType.THIS_ROUND` already exists. The self-discard is a straightforward `SelectStep` over `played_cards` + `DiscardCardStep`.

**Existing steps/filters needed:** `SelectStep`, `DiscardCardStep`, `CreateEffectStep`, `PlayedCardFilter`
**New steps/filters needed:** None
**Engine changes needed:** None

---

### Battle Fury — ULTIMATE (PURPLE)

**Effect text:** "Each time after one of your resolved cards is discarded, you may perform its primary action."

**This is a triggered passive ability** that fires whenever a resolved card enters the discard pile.

**Implementation challenges:**

1. **New PassiveTrigger needed:** `AFTER_CARD_DISCARD` — no existing trigger fires on card discard events. The engine currently has `BEFORE_ATTACK`, `BEFORE_MOVEMENT`, `BEFORE_SKILL`, `AFTER_BASIC_ACTION`, `AFTER_ATTACK`, `AFTER_PUSH`, `AFTER_PLACE_MARKER`. None cover discard events.

2. **Trigger integration point:** Where do cards get discarded?
   - `DiscardCardStep.resolve()` — explicit discard
   - `ForceDiscardStep` / `ForceDiscardOrDefeatStep` — forced discard by enemies
   - `FinalizeHeroTurnStep` — end-of-turn discard of resolved cards
   - Potentially other sources
   
   The passive must hook into ALL discard paths that discard a "resolved card."

3. **"Perform its primary action":** After the discard triggers, the engine needs to:
   - Identify the discarded card's primary action (ATTACK, SKILL, MOVEMENT)
   - Ask Garrus "You may perform [card]'s primary action" (optional)
   - If accepted, push the appropriate secondary action step onto the stack (e.g., an `AttackSequenceStep` with the card's attack value, or `MoveSequenceStep` with movement value)
   - The card is already in discard at this point — the action is performed "from memory"

4. **Scope:** "Resolved cards" means any card in `hero.played_cards` (these are already marked `CardState.RESOLVED`). The passive triggers whenever such a card is discarded — e.g., via Chilling Howl's self-discard, an enemy's forced discard (Pilum-style), or any other effect that moves a played card to the discard pile.

5. **Chaining is allowed:** If the triggered primary action itself causes another of Garrus's resolved cards to be discarded, Battle Fury may trigger again on that new discard. This is intended — the passive is designed to cascade through discard events. No re-entrancy guard is needed; just push triggered actions onto the stack as they occur and let the normal resolution flow handle them.

**Difficulty: HARD** — This requires:
- New `PassiveTrigger.AFTER_CARD_DISCARD` enum value
- Hook into `DiscardCardStep` (and `ForceDiscardStep` / `ForceDiscardOrDefeatStep`) to check for passive triggers after a card moves from `played_cards` to the discard pile
- Logic to "perform primary action" from a card that's now in discard — essentially reconstructing a basic action step from card data
- Qualification check: only fires if the discarded card was in Garrus's `played_cards` at time of discard (i.e., was a resolved card belonging to Garrus)

**Existing steps/filters needed:** Existing action steps (`AttackSequenceStep`, `MoveSequenceStep`, etc.) as the "perform primary action" payload
**New steps/filters needed:**
- A `PerformPrimaryActionStep` that reads a card's primary action and pushes the corresponding basic step
**Engine changes needed:**
- Add `PassiveTrigger.AFTER_CARD_DISCARD` to enums
- Add passive trigger check in `DiscardCardStep.resolve()` (after successful discard)
- Add passive trigger check in `ForceDiscardStep` / `ForceDiscardOrDefeatStep` (after discard branch)
- Implement `get_passive_steps()` for Battle Fury that reads the discarded card and pushes the appropriate action

---

## Difficulty Summary

| Card(s) | Family | Difficulty | New Engine Work |
|----------|--------|------------|-----------------|
| Hold Ground / Make a Stand / Battle Ready | Conditional Retrieval | **EASY** | None |
| Light Pilum / Heavy Pilum | Forced Discard | **EASY** | None |
| Angry Strike | Scaling Attack | **EASY** | None |
| Menace / Threaten / Terrify | Push Enemies | **EASY** | None |
| Form Up! / Testudo! | Pull Friendlies | **EASY** | None |
| Trace / Chase / Hunt Down | Charge Attack | **EASY** | None |
| Chilling Howl | Movement Restriction | **EASY** | None |
| Blunt Force / Send Flying | Dash + Push | **MEDIUM** | Add `ignore_obstacles` to `PushUnitStep` (with legal-landing + preserved traversal triggers) |
| Battle Fury (Ultimate) | Triggered Passive | **HARD** | New `PassiveTrigger`, hook discard events, reconstruct actions from discarded cards |

## Recommended Implementation Order

1. **Conditional Retrieval** (Hold Ground / Make a Stand / Battle Ready) — simplest, establishes test patterns
2. **Forced Discard** (Light Pilum / Heavy Pilum) — uses existing steps directly
3. **Angry Strike** — simple scaling attack
4. **Push Enemies** (Menace / Threaten / Terrify) — introduces repeat pattern for Garrus
5. **Pull Friendlies** (Form Up! / Testudo!) — mirror of push enemies
6. **Charge Attack** (Trace / Chase / Hunt Down) — branching choice pattern
7. **Chilling Howl** — movement restriction, similar to Arien's Deluge
8. **Dash + Push** (Blunt Force / Send Flying) — requires `PushUnitStep` enhancement
9. **Battle Fury** (Ultimate) — hardest, new trigger system, implement last

## Engine Changes Summary

| Change | Impact | Cards |
|--------|--------|-------|
| `PushUnitStep.ignore_obstacles: bool = False` (path passes through obstacles, final hex must be legal, traversal triggers like mines still fire) | Low-Medium — extend passable-token logic + land validation | Blunt Force, Send Flying |
| `PassiveTrigger.AFTER_CARD_DISCARD` | Medium — new enum + hook in discard steps | Battle Fury |
| Passive check in `DiscardCardStep` | Medium — needs careful integration | Battle Fury |
| Action reconstruction from discarded card | Medium — new step or logic | Battle Fury |
