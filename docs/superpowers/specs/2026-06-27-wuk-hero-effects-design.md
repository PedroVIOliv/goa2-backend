# Wuk Hero Effects — Design Spec

**Date:** 2026-06-27
**Hero file:** `src/goa2/data/heroes/wuk.py` (deck already defined; effects unimplemented)
**Effects file (new):** `src/goa2/scripts/wuk_effects.py`

## Overview

Wuk is a Tree-token-centric hero. The deck has 16 cards + 1 ultimate, organized into
9 mechanical groups. The central new mechanic is the **Tree token**: a standard board
token Wuk places, swaps with, removes (as a cost), and uses as a targeting anchor.

This spec covers all 9 groups, including **Trample / Angry Stampede** (Group I).

### Confirmed rules (from designer)

- **Tree tokens**: standard tokens, **supply = 3**, **persist end-of-round** (like Zombie
  tokens). Block **movement only** (non-passable), do **not** block ranged line of sight
  (engine ignores LoS by default per rule 4.1, so no special handling needed).
- **"Remove a Tree token" is a required cost** for the retrieve cards and Tree Slam's
  second mode — if no Tree token is available in range, that branch cannot be performed.
- **Throw cards** can throw **any token on the board** (any type) OR an enemy unit.
- **March of Nature** fires **after each card Wuk plays as his action** (primary/secondary)
  on his own turn — not on defense reactions.
- **Mystic Saplings' "not removed at end of round" clause is redundant** — all Tree tokens
  persist regardless of source.

## New Shared Infrastructure (build first)

### 1. `TokenType.TREE`
- Add `TREE = "tree"` to `TokenType` in `domain/models/enums.py`.
- Add `TokenType.TREE: 3` to `TOKEN_SUPPLY` in `domain/models/token.py`.
- In `engine/setup.py` `_initialize_token_pool`, add `TokenType.TREE` to the
  `persists_end_of_round` set so all 3 trees persist. Default `is_passable=False`
  (blocks movement). No new `Token` model fields needed.

### 2. Minion-battle exclusion effect (Dominance)
- New `EffectType.MINION_BATTLE_EXCLUSION` in `domain/models/enums.py` (+ effect model
  plumbing in `domain/models/effect.py` if required for the discriminated union).
- Created via `CreateEffectStep` anchored on Wuk, `duration=THIS_ROUND`, `max_value=N`
  (1 for Claim Dominance, 2 for Assert Dominance). **No targeting at cast time.**
- Modify `_resolve_minion_battle` (`engine/steps/combat.py:~1132`): after computing
  `red_count` / `blue_count`, **group active `MINION_BATTLE_EXCLUSION` effects by origin
  hero**. For each origin hero H:
  1. Resolve H's hex and team; `enemy_team` = the opposing team.
  2. Build the **set** of `enemy_team` minions adjacent to H that are inside the active zone
     (**regardless of immunity** — heavy/immune minions are still counted as adjacent).
  3. `cap = sum(effect.max_value for that hero's exclusion effects)`.
  4. `reduction = min(cap, len(adjacent_set))`.
  5. Subtract `reduction` from `enemy_team`'s count.
- **Why sum the caps but use a set of minions:** each card grants an independent "up to N"
  allowance (allowances **add**: Claim 1 + Assert 2 = 3 slots), but a single minion can only
  be excluded once (minions are a **set**, so dedup is automatic). The final reduction is
  therefore `min(Σ caps, distinct adjacent enemy minions)`. Worked examples:
  - 3 adjacent, Assert(2) only → `min(2, 3) = 2`.
  - 2 adjacent, Claim(1) + Assert(2) → `min(3, 2) = 2` (no phantom 3rd minion).
  - 5 adjacent, Claim(1) + Assert(2) → `min(3, 5) = 3` (both allowances usable).
- **Multiple effects same round CAN occur** (a future effect may let Wuk resolve a second
  card). The per-origin grouping + summed caps + minion set handles any number of stacked
  exclusion effects. If two *different* origin heroes ever held exclusion effects (not
  possible with a single Wuk), dedup the adjacent set across origins so no minion on a given
  enemy team is excluded more than once.

### 3. `AFTER_RESOLVE_CARD` passive trigger (March of Nature)
- Add `AFTER_RESOLVE_CARD = "after_resolve_card"` to `PassiveTrigger` in
  `domain/models/enums.py`.
- Fire `CheckPassiveAbilitiesStep(trigger=AFTER_RESOLVE_CARD)` at the end of the action
  step list in `ResolveCardStep` (`engine/steps/cards.py:~748`), after the existing
  AFTER_ATTACK / AFTER_MOVEMENT / AFTER_BASIC_ACTION checks. It runs for the acting
  hero's played card; only Wuk's ultimate listens for it, so it is naturally scoped.

### 4. No new filter for tree-adjacency targeting
- Reuse `CountMatchFilter` (`engine/filters_composite.py`) with `include_tokens=True`:
  ```python
  CountMatchFilter(
      include_tokens=True,
      min_count=1,
      sub_filters=[
          TokenTypeFilter(token_type=TokenType.TREE),
          RangeFilter(max_range=1, origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY),
      ],
  )
  ```
  Candidate enemy unit resolves to its hex; passes if ≥1 Tree token sits adjacent.

### 5. Throw placement
- Throw places a selected token **or** enemy unit into an empty hex within range (a
  teleport, not pathed movement). Use `PlaceUnitStep` for both. If `PlaceUnitStep` does
  not currently handle a token id, extend it so it does (designer-approved).

### 6. `MoveSequenceStep.allow_straight_line_through_obstacles` (Trample)
- New flag `allow_straight_line_through_obstacles: bool = False` on `MoveSequenceStep`
  (`engine/steps/movement.py`).
- When set, replace the destination filter with a single `OrFilter`:
  ```python
  OrFilter([
      AndFilter([
          ObstacleFilter(is_obstacle=False, exclude_id=actor),
          MovementPathFilter(range_val=effective_range, unit_id=actor,
                             pass_through_obstacles=False),
      ]),  # normal reachable destinations
      AndFilter([
          ObstacleFilter(is_obstacle=False, exclude_id=actor),
          InStraightLineFilter(origin_id=actor),
          StraightLinePathFilter(origin_id=actor, pass_through_obstacles=True),
          MovementPathFilter(range_val=effective_range, unit_id=actor,
                             pass_through_obstacles=True),
      ]),  # straight-line, ignoring obstacles
  ])
  ```
- `effective_range` keeps the existing MOVEMENT_ZONE capping, so the offered list is
  zone-correct. The spawned `MoveUnitStep` runs with `pass_through_obstacles=True`; it only
  ever receives filter-approved hexes, so this is safe.
- No "trample mode" declaration: the through-effects (Group I) key off
  `BetweenHexesFilter(move_origin → move_dest)`, which is empty for any non-straight move.
  A straight-line destination crossing enemies triggers trample; a bendy/normal one does
  not. This matches "if you move in a straight line" exactly.

## Per-Card Design

Tier variants share a base class (Tali/Misa pattern). `*_effects.py` lives in
`src/goa2/scripts/` and is imported so `@register_effect` runs.

### Group A — Throw: `toss_away`, `mighty_throw`, `monstrous_throw`
"Place a token, or an enemy unit, adjacent to you into a space in range."
1. `SelectStep(UNIT_OR_TOKEN)` adjacent to Wuk, filtered to *(any token) OR (enemy unit)*.
2. `SelectStep(HEX)` empty, non-obstacle, within `stats.range` of Wuk.
3. Place the selected entity there (see Infra #5).
- `monstrous_throw` wraps 1–3 in `MayRepeatOnceStep`.

### Group B — Canopy swap: `into_the_canopy`, `treetop_ride`
"Choose one — Swap with a Tree token in radius. / Swap a friendly unit in radius with a
Tree token in radius."
- `SelectStep(NUMBER)` choose mode:
  - Mode 1: `SwapUnitsStep(unit_a_id=hero.id, unit_b_key=<tree>)` where tree selected via
    `TokenTypeFilter(TREE) + RangeFilter(radius)`.
  - Mode 2: select friendly unit in radius + tree in radius → `SwapUnitsStep`.
- `treetop_ride`: wrap the choose-one block in `MayRepeatNTimesStep(max_repeats=1)`
  ("choose up to two times"); each iteration re-picks a mode.
- Friendly-unit mode excludes Wuk (Mode 1 already covers Wuk).

### Group C — Dominance: `claim_dominance` (N=1), `assert_dominance` (N=2)
"This round: Up to N enemy minions adjacent to you do not count toward the minion total
during minion battle, regardless of immunity."
- Single `CreateEffectStep(MINION_BATTLE_EXCLUSION, THIS_ROUND, max_value=N)` on Wuk.
- All counting/exclusion logic lives in `_resolve_minion_battle` (Infra #2). No selection.

### Group D — Retrieve: `gifts_of_nature`, `tree_of_plenty`, `abundance`
"Remove a Tree token in radius. [Choose] retrieve a discarded card / friendly hero
retrieve."
1. `SelectStep(UNIT_OR_TOKEN)` tree in radius, `TokenTypeFilter(TREE)`, **`is_mandatory=True`
   (required cost)** → `RemoveTokenStep`. No tree in radius → branch aborts.
2. Retrieve:
   - `gifts_of_nature`: self retrieve (`RetrieveCardStep`, optional "you may").
   - `tree_of_plenty`: choose one — self retrieve OR friendly-hero retrieve
     (reuse Tali's `_friendly_retrieve_steps`).
   - `abundance`: choose one **or both** — self retrieve and/or friendly retrieve.

### Group E — Nature's weapon: `natures_protector`, `natures_guardian`, `natures_champion`
"Choose one [Champion: one or both, on different targets] — Target a hero adjacent to you.
/ Target a unit in range adjacent to a Tree token."
- `SelectStep(NUMBER)` choose mode (Champion offers both on different targets, tracked via
  `ExcludeIdentityFilter`):
  - Mode 1: enemy **hero** adjacent (range 1).
  - Mode 2: enemy unit within `stats.range` + `CountMatchFilter` tree-adjacency (Infra #4).
- `AttackSequenceStep(damage=stats.primary_value, is_ranged=True)` (cards are ranged; both
  modes set `is_ranged=True` per the ranged-card convention).

### Group F — Mystic Saplings (Silver): `mystic_saplings`
"Place up to 3 Tree tokens in radius."
- Optional-chain place loop (Tali `_place_ice_steps` pattern): up to 3 iterations, each
  `SelectStep(HEX, optional, active_if previous placed)` + `PlaceTokenStep(TREE)`.
- Trees persist by default (Infra #1), so no per-placement flag needed.

### Group G — Tree Slam (Gold): `tree_slam`
"Choose one — Target a minion adjacent to you. / Remove a Tree token adjacent to you.
Target a unit in range."
- `SelectStep(NUMBER)` choose mode:
  - Mode 1: `AttackSequenceStep` vs enemy **minion** adjacent (range 1).
  - Mode 2: `SelectStep(UNIT_OR_TOKEN)` tree adjacent, **`is_mandatory=True` (cost)** →
    `RemoveTokenStep` → `AttackSequenceStep` vs any enemy unit within `stats.range`.

### Group H — March of Nature (Ultimate, passive): `march_of_nature`
"Each time after you resolve a card, you may place a Tree token in radius."
- `PassiveConfig(trigger=AFTER_RESOLVE_CARD, uses_per_turn=0, is_optional=True)`.
- `get_passive_steps`: optional `SelectStep(HEX)` within radius 3 of Wuk + empty/non-obstacle
  → `PlaceTokenStep(TREE)`. Overflow (all 3 trees placed) handled by existing
  `PlaceTokenStep` (prompts to remove an existing tree first).

### Group I — Trample: `trample` (minions N=1), `angry_stampede` (minions N=2)
"If you move in a straight line: You may ignore obstacles; each enemy hero you moved
through discards a card, or is defeated; defeat up to N minions you moved through."
- Primary MOVEMENT action (value 4). Steps:
  1. `RecordHexStep(unit_id=hero.id, output_key="move_origin")`.
  2. `MoveSequenceStep(unit_id=hero.id, range_val=stats.primary_value,
     destination_key="move_dest", allow_straight_line_through_obstacles=True)` — single
     zone-aware destination list mixing normal and straight-line-through-obstacle hexes
     (Infra #6). No separate number/mode prompt.
  3. **Crossed enemy heroes (all, mandatory):** collect every enemy hero matching
     `BetweenHexesFilter(move_origin → move_dest)`, `TeamFilter(ENEMY)`,
     `UnitTypeFilter(HERO)`, **and `ImmunityFilter()`** (so an immune hero — e.g.
     `IMMUNITY_ENEMY_ACTIONS` / active attack-immunity — is skipped), then apply
     `ForceDiscardOrDefeatStep` to each. Either collect mechanism is acceptable
     (`MultiSelectStep` auto-all vs repeat-until-none loop) — settled at plan time.
  4. **Crossed minions (up to N, sequential — NOT a single MultiSelect):** for `trample`
     one `SelectStep`+`DefeatUnitStep` pair; for `angry_stampede` two pairs. Each
     `SelectStep` filters `BetweenHexesFilter`, `TeamFilter(ENEMY)`, `UnitTypeFilter(MINION)`,
     `ImmunityFilter()`, `ExcludeIdentityFilter([already-defeated keys])`, `is_mandatory=False`,
     followed by `DefeatUnitStep` + `RecordTargetStep`. Sequential selects re-evaluate
     `ImmunityFilter` each time, so defeating a normal minion that was supporting a heavy
     strips the heavy's immunity and makes it selectable in the next pair. **This ordering
     freedom is the reason for separate steps.**
- For non-straight moves, step 2 still works as a normal move and `BetweenHexesFilter`
  returns empty in steps 3–4, so no trample effects occur.

## Edge Cases

- **Supply exhausted (3 placed):** `PlaceTokenStep` already prompts the owner to remove an
  existing Tree token before placing — reused for Mystic Saplings and March.
- **Required-cost branches with no tree:** mandatory tree `SelectStep` aborts that branch
  cleanly; the rest of the card (if any) follows normal mandatory-step skip rules.
- **Dominance, Wuk outside active zone:** no adjacent in-zone enemy minions → zero
  reduction. Computed dynamically at battle time.
- **Dominance "regardless of immunity":** counting uses raw adjacency, not the immunity
  filter, so heavy/immune minions are still excluded from the count.
- **Champion both-on-different-targets:** second target uses `ExcludeIdentityFilter` on the
  first target's key.
- **Trample, heavy + supporting minion both crossed:** sequential minion select+defeat
  pairs let the player defeat the support first, stripping the heavy's immunity before the
  next selection (see Group I).
- **Trample, non-straight move:** `allow_straight_line_through_obstacles` still permits a
  normal move; `BetweenHexesFilter` yields nothing, so no through-effects fire.

## Open Items

- None outstanding. (Trample / Angry Stampede now specced as Group I.)

## Testing

- One test file per group in `tests/engine/` (`test_wuk_<group>.py`), following the
  `goa2-card-effect-tests` skill (EffectScenarioBuilder + `run_card`, raw-stack fallback
  for step isolation).
- Dedicated unit tests for new infrastructure:
  - `MINION_BATTLE_EXCLUSION`: count reduction with/without Wuk adjacency, single-effect
    `min(N, adjacent)`, stacked Claim+Assert `min(Σ caps, distinct adjacent)` across the
    three worked examples, immune minions still counted as adjacent.
  - `AFTER_RESOLVE_CARD` trigger + March passive: tree placed after a played card; offer
    suppressed on defense reactions; overflow removal at 3 trees.
  - Tree token setup: supply 3, persists end-of-round, blocks movement, doesn't block
    ranged targeting.
  - `MoveSequenceStep.allow_straight_line_through_obstacles`: destination list includes
    straight-line-through-obstacle hexes AND normal hexes, both capped by MOVEMENT_ZONE.
  - Trample / Angry Stampede: straight move crosses heroes (all discard-or-defeat) and
    minions (up to N); heavy+support ordering case (defeat support first, then heavy);
    non-straight move triggers no through-effects.
- Full suite green before merge: `PYTHONPATH=src uv run pytest tests/ -q`.

## Client-Contract Touchpoints (per CLAUDE.md)

- New `StepType` values for any new steps → add to `AnyStep` union in `engine/step_types.py`.
- New `EffectType.MINION_BATTLE_EXCLUSION`, `TokenType.TREE`, `PassiveTrigger.AFTER_RESOLVE_CARD`
  are enum additions (serialization-safe).
- New `GameEvent`s already exist for token place/remove/move; reuse them. If a new
  observable event is needed (e.g., battle-exclusion applied), add a `GameEventType` value
  and document in `CLIENT_INTEGRATION_GUIDE.md`.
