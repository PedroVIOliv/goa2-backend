# Effect → Card Attribution and One-Instance-Per-Card

**Date:** 2026-08-03
**Status:** Approved for planning

## Problem

Two defects in how `ActiveEffect`s bind to the card that created them.

### 1. Misattribution when performing another card's action

`CreateEffectStep` resolves its card binding from `context["current_card_id"]`
(`engine/steps/effects.py:117-129`). Only `ResolveCardTextStep`
(`engine/steps/cards.py:589`), the action chooser (`cards.py:678`) and turn start
(`engine/steps/phases.py:40`) ever set that key. Every step that re-performs a
*different* card's action calls `effect.build_steps(...)` directly and leaves the
key pointing at the granting card, so the copied card's effects bind to the
wrong card.

Reproduced against the engine: pushing two `PerformPrimaryActionStep`s for
Dodger's `enfeeblement` while `current_card_id` names the granting card yields

```
eff_e_1 area_stat_modifier  source_card_id=card_granting
eff_e_2 repeat_prevention   source_card_id=card_granting
eff_e_3 area_stat_modifier  source_card_id=card_granting
eff_e_4 repeat_prevention   source_card_id=card_granting
```

Four rows on a card that created none of them. The effects' `is_active`
toggling and `expire_by_card` lifecycle now follow the granting card instead of
the card whose text produced them.

### 2. Repeats duplicate active effects

Game rule: *only one instance of an active effect per card can be active;
repeating an active effect does not duplicate it.*

`EffectManager.create_effect` (`engine/effect_manager.py:79`) has no general
dedup — `state.add_effect` simply appends. The only guard is a special case for
`BASIC_ACTION_STAT_BONUS` (`effect_manager.py:103-114`), added for Cordelia's
Broom family. Every other effect type stacks on repeat, as the `eff_e_3` /
`eff_e_4` rows above show.

## Non-goals

- Collapsing cards that legitimately need several payloads (Brogan's Bulwark:
  self + friendlies; Dodger's Enfeeblement: `-6` Attack + no repeats) into a
  single `ActiveEffect` row. Those stay as multiple rows; the invariant is
  enforced per `(card, effect_type, scope)`, which is what makes repeats
  idempotent without touching any card script.
- Changing `ActiveEffect`, `EffectScope` or `GameEvent` shapes. No client
  contract changes.

## Design

### Effect identity: dedup in `EffectManager.create_effect`

When `source_card_id` is set, search `state.active_effects` for a row with the
same `(source_card_id, effect_type, scope)`. On a hit, return that row unchanged
and create nothing.

- Scope comparison is Pydantic model equality on `EffectScope` — `shape`,
  `range`, `origin_id`, `origin_hex`, `affects`, `direction`.
- The match ignores `is_active`, so a present-but-deactivated row still blocks a
  duplicate.
- On a hit nothing about the existing row changes: payload, `max_value` charges,
  `created_at_turn` / `created_at_round`, and exception lists (
  `except_attacker_ids`, `except_card_colors`) all stay as they were. A repeat
  cannot refresh a spent effect, re-point it, or restart its duration.
- Effects with `source_card_id is None` (token effects, engine-internal delayed
  triggers from `ScheduleJourneyReturnStep`, `SetCardInitiativeStep`, etc.) are
  never deduped.
- A hit returns immediately with no side effects at all, including no
  `card.is_active` write. This follows the "leave it untouched" rule and the
  existing `BASIC_ACTION_STAT_BONUS` precedent: a card whose row was
  deliberately deactivated (turned facedown) must not be reactivated by a
  repeat. `card.is_active = True` is still set on the create path.

This replaces the `BASIC_ACTION_STAT_BONUS` special case, which it subsumes:
same card, same type, same hero-anchored scope.

Card ids are safe as a dedup key — all 600 card ids across the 32 registered
heroes are unique, so two heroes cannot collide on one key.

### Attribution: bind the card at build time

New module-level helper in `engine/effects.py`:

```python
def bind_effect_cards(steps: list[GameStep], card_id: str) -> list[GameStep]:
```

It walks the step tree and, for every `CreateEffectStep` with
`source_card_id is None` and `is_token_effect is False`, sets
`source_card_id = card_id`. Steps that already name a card explicitly are left
alone.

The walk is generic: it iterates `model_fields` and recurses into any field
holding a `GameStep` or `list[GameStep]`. That covers `steps_template`
(`MayRepeatNTimesStep`, `MayRepeatOnceStep`, `ForEachStep`), `finishing_steps`
(`CreateEffectStep`) and `new_steps` today, and any nested-step field added
later without further maintenance.

`CardEffect` funnels every public entry point through it:

| Entry point | Card bound |
|---|---|
| `get_steps(state, hero, card)` | `card` |
| `get_defense_steps(state, defender, card, context)` | the defense card |
| `get_on_block_steps(state, defender, card, context)` | the defense card |
| `get_steps_with_stats(state, hero, card, stats)` *(new)* | `card` |

`get_steps_with_stats` exists for callers that compute `CardStats` themselves.
The four engine sites that currently reach past the public API and call
`build_steps` directly switch to it:

- `engine/steps/cards.py:1801` — `PerformPrimaryActionStep` (defect 1)
- `engine/steps/cards.py:2062` — `PerformCardActionStep` (NebKher's Mind Grip)
- `engine/steps/movement.py:1756` — primary MOVEMENT via `MoveSequenceStep`
- `engine/steps/utility.py:1002` — red-card build

After this, effects bind to the card whose text created them even when that card
belongs to another hero (Mind Grip) or is already resolved (Bullet Time).

### Dormancy for cards that will never resolve

*(Added during implementation — not in the original design.)*

Card-bound effects are dormant until their card resolves: `_is_effect_active`
returns `False` while `effect.source_card_id and not effect.is_active`, and
`FinalizeHeroTurnStep` flips them on via `activate_effects_by_card`. That hook
only ever fires for a hero's **current turn card**.

Binding a re-performance to the performed card therefore breaks it: an effect
created from an already-resolved card (Bullet Time) or from an enemy's card
(Mind Grip) would wait for an activation that never comes. `create_effect` now
starts an effect active when its bound card is in any state other than
`UNRESOLVED` — dormancy models "played, but not yet resolved", and everything
else is already in force.

### Context inference becomes vestigial

`CreateEffectStep.resolve` keeps its `current_card_id` fallback and the
`use_context_card` field — removing the field would break persisted step JSON —
but nothing built through the effect API reaches it any more.

The `defense_card_id` branch added in b79abef is reverted: build-time binding
already attributes defense effects to the defense card, and leaving the branch
in place would keep a second, divergent source of truth. The tests from b79abef
stay and must still pass.

## Testing

**`tests/engine/test_effect_creation_steps.py`**
- A second `create_effect` with identical `(card, type, scope)` returns the
  identical row object and leaves `state.active_effects` at length 1.
- Differing `scope` or `effect_type` creates a second row.
- `source_card_id=None` never dedups.
- A row whose `max_value` has been decremented is not refreshed by a repeat.
- Dedup hits a row with `is_active=False`.

**Attribution regressions**
- Re-performing card Y while resolving card X binds Y's effects to Y. The
  four-row reproduction above becomes two rows on `enfeeblement`.
- `PerformCardActionStep` binds to the enemy's card.
- Defense and on-block effects still bind to the defense card (b79abef's Arien
  duelist tests).

**Card-level (`tests/engine/effects/cases/`)**
- Brogan Bulwark: 2 rows on first play, still 2 after a repeat.
- Dodger Enfeeblement: 2 rows on first play, still 2 after a repeat.

**Guardrail (`tests/engine/test_steps_package_guardrails.py`)**
- AST-scan `src/goa2/engine/` for `.build_steps(` call sites; allow only
  `engine/effects.py`. Forces future callers through the binding wrapper.

## Risks

- **Cordelia.** The `BASIC_ACTION_STAT_BONUS` special case is removed in favour
  of the generic dedup, but Cordelia lives on local `main` (`f55de05`) and is
  not present on this branch's base (`origin/main`). Her Broom-family scope is
  hero-anchored and should match by equality, but after merging, re-run
  `tests/engine/effects/cases/test_cordelia_effects.py` to confirm
  re-performance still reuses the single bonus row.
- **Scope equality is exact.** A card whose effect scope varies per performance
  (dynamic `origin_id_key` pointing at a freshly selected target) would still
  create a second row on repeat. No card-bound effect does this today — every
  `origin_id_key` user is a token effect, which is exempt by design — but the
  rule is per `(card, type, scope)`, not per card, and that gap is deliberate.
- **Effects on cards not in play.** Binding to the performed card means
  `card.is_active` can be set on a card sitting in the discard or hand (e.g.
  Tigerclaw performing a basic card). This already happens today for
  re-performed played cards; the change makes it correct rather than new.
