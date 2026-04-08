# Min: High-Level Design for Card Effects

## Goal

Design Min’s 18 card effects using the current stack-based effect engine, identifying:
- What is **easy now** (existing steps/filters)
- What needs **new composition/helpers**
- What needs **new steps/filters**
- What likely needs **engine/system changes**

---

## Current Engine Capabilities Relevant to Min

Already available and reusable:
- Attack, move, push, swap, place flows (`AttackSequenceStep`, `MoveUnitStep`, `PushUnitStep`, `SwapUnitsStep`, `PlaceUnitStep`)
- Selection/filter composition (`SelectStep`, `RangeFilter`, `TeamFilter`, `CardsInContainerFilter`, etc.)
- Repeat scaffolding (`MayRepeatNTimesStep`)
- Delayed resolution via active effects (`CreateEffectStep` + `EffectType.DELAYED_TRIGGER` + `finishing_steps`)
- Discard/defeat resolution (`ForceDiscardStep`, `ForceDiscardOrDefeatStep`)
- Marker framework (`PlaceMarkerStep`, `RemoveMarkerStep`) — currently marker types are limited

Notably missing for Min:
- Passive trigger for “after you perform an attack action” (no `AFTER_ATTACK` in `PassiveTrigger`)
- Mine token subtypes / facedown trap token lifecycle
- Generic “double item bonuses” effect type
- Permanent “dashboard item from deck” system
- Canonical “line-between actor and target” target-prevention primitive for Smoke Bomb wording

---

## Card-by-Card Feasibility

### A) Easy with existing steps/filters (implement first)

1. **Crane Stance** (`crane_stance`)  
   Attack adjacent, then push adjacent enemy up to 3.

2. **Viper Stance** (`viper_stance`)  
   Attack adjacent, then optional smoke-bomb swap.

3. **Vanish** (`vanish`)  
   Defense text: swap with Smoke Bomb in range; if swapped, block.

4. **Poof!** (`poof`)  
   Same implementation pattern as Vanish with different range.

5. **Ruse** (`ruse`)  
   Vanish + optional post-swap re-placement of Smoke Bomb.

---

### B) Moderate: new composition/helper logic, no deep engine rewrite

6. **Tiger Stance** (`tiger_stance`)  
   Attack → move adjacent to target (1) → push adjacent enemy up to 3.

7. **Dragon Stance** (`dragon_stance`)  
   Tiger variant with movement 1–2 to target-adjacent space.

8. **Cobra Stance** (`cobra_stance`)  
   Viper variant plus optional Smoke Bomb re-placement after swap.

9. **Fast as Lightning** (`fast_as_lightning`)  
   Attack at range, then apply “after attack” text of resolved/discarded red card.  
   Needs helper policy for selecting which eligible red card is used.

10. **Smoke Bomb** (`smoke_bomb`)  
    Place token; enforce target-prevention when token is on straight line between attacker and target.  
    Likely needs a dedicated filter/helper for “line between two units” semantics.

---

### C) New step/filter/effect types likely needed

11. **Inner Strength** (`inner_strength`)  
    “This round: Double your item bonuses.”  
    Needs a dedicated stat-scaling effect type (or equivalent multiplier mechanism).

12. **Perfect Self** (`perfect_self`)  
    Option A: same doubling as Inner Strength.  
    Option B: choose Tier II card from deck and add as permanent dashboard item.  
    Requires both stat-doubling support and permanent-item support.

13. **Death Grenade** (`death_grenade`)  
14. **Holy Death Grenade** (`holy_death_grenade`)  
    Place grenade token, then end-of-turn discard-or-defeat for adjacent enemy heroes (1 or 2), remove token.  
    Best implemented as delayed-trigger effect + grenade marker/token type + cleanup step.

---

### D) Engine/system changes (largest scope)

15. **Trip Mine** (`trip_mine`)  
16. **Cluster Mine** (`cluster_mine`)  
17. **Minefield** (`minefield`)  
    Requires facedown mine tokens with hidden blast/dud identity, movement-through interaction hooks, reveal/removal, and conditional discard on blast count.

18. **Flurry of Blows** (`flurry_of_blows`, passive ultimate)  
    “Each time after you perform an attack action, you may repeat it once on a different target.”  
    Requires new passive trigger semantics and robust “repeat attack on different target” enforcement.

---

## Proposed Delivery Phases

## Phase 1 — Quick wins (existing primitives)
- `crane_stance`, `viper_stance`, `vanish`, `poof`, `ruse`

## Phase 2 — Composite implementations
- `tiger_stance`, `dragon_stance`, `cobra_stance`, `fast_as_lightning`, `smoke_bomb`
- Add small helpers/filters only (no core engine rewrites)

## Phase 3 — New effect/step capabilities
- `inner_strength`, `perfect_self`, `death_grenade`, `holy_death_grenade`
- Introduce generic doubling and grenade delayed-trigger lifecycle

## Phase 4 — Engine-level mechanics
- `trip_mine`, `cluster_mine`, `minefield`, `flurry_of_blows`
- Add trap-token subsystem + passive after-attack trigger model

---

## Recommended Technical Decisions (before implementation)

1. **Fast as Lightning card selection rule**
   - Most-recent eligible red card vs player choice.

2. **Smoke Bomb targeting geometry**
   - Define exact “between” semantics for hex grid and adjacency edge cases.

3. **Item doubling semantics**
   - Whether doubling applies to all derived card stats uniformly and how it stacks.

4. **Permanent dashboard items**
   - Persistence model (hero field, serialization, UI view exposure).

5. **Mine token model**
   - Token identity visibility lifecycle, reveal timing, and multi-token movement interactions.

6. **Flurry trigger boundary**
   - Define “attack action” scope (primary vs repeated/generated attacks) to avoid infinite loops.

---

## Minimal Architecture Impact Summary

- **No core changes needed:** 5 cards  
- **Light composition/helpers:** 5 cards  
- **New step/filter/effect primitives:** 4 cards  
- **Core engine expansion:** 4 cards

This phased approach enables early playable Min support while de-risking the hardest mechanics (mines + passive repeat attacks) behind explicit engine milestones.
