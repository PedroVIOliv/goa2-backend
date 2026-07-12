# Takahide Hero Implementation Plan

> **Status: COMPLETE (2026-07-11).** All 13 tasks shipped on `main`. See the
> TDD paths doc's header for the deviations decided during implementation.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Takahide's 19 card effects + Ready for War ultimate on top of four new engine primitives (starts-in-deck setup, deck-card swap step, facedown-outside-hand masking, empty-hex-obstacle effect), fully TDD per the approved paths doc.

**Architecture:** Effects are assembled from existing steps around one shared helper (`_ally_discard_gate`, the "a friendly hero may discard / if that hero has a card in the discard" pipeline, built from `SelectStep` + `DiscardCardStep` + `CountCardsStep` + `CheckContextConditionStep` — Brogan Throwing Spear precedent). New primitives: `Card.starts_in_deck` (P1), `SwapWithDeckCardStep` (P2), facedown masking in views/selection (P3), `EMPTY_HEX_OBSTACLE` `EffectType` (P4, Wasp `STATIC_BARRIER` template), plus the `on_ultimate_unlocked` one-shot (P5, Ursafar template).

**Tech Stack:** Python 3.11+, Pydantic V2, pytest. Run tests: `PYTHONPATH=src uv run pytest tests/ -q`.

## Global Constraints

- **REQUIRED READING before any task:** `docs/superpowers/plans/2026-07-11-takahide-tdd-paths.md` — its per-card **H/U paths are the authoritative test list**: every path of the sections a task covers becomes at least one test (exemplar tests in this plan show the style, not the full list). Its "Locked interpretations" (1–15) and spec decisions S1–S17 are binding.
- Also read `docs/EFFECT_AUTHOR_REFERENCE.md` and `src/goa2/scripts/brogan_effects.py` (`ThrowingSpearEffect` at ~line 556 — the exact discard-gate pattern) before writing effect code.
- Commit directly on `main`. No `Co-Authored-By` lines, no AI-tool mentions in commits.
- New steps MUST add a unique `StepType` in `domain/models/enums.py` and set it as the class `type` default (import-time guard raises otherwise). New `EffectType` values go in `domain/models/effect.py`. Anything visible in views/events is client contract — update `docs/CLIENT_INTEGRATION_GUIDE.md` where a task says so.
- Steps that change observable state MUST emit `GameEvent`s; player input MUST use `create_input_request()` — never raw dicts.
- Range/radius/adjacency checks use **topology distance** (pathfinding) — existing `RangeFilter` already does this; don't hand-roll distance. ONE exception: the `EMPTY_HEX_OBSTACLE` radius test uses raw cube distance to avoid obstacle-definition recursion (Task 2, mirrors Wasp).
- Immunity blocks ALL selections, friendly and enemy alike (Brynn precedent "immunity blocks all"; Snorri S10): every hero-selection `SelectStep` in this plan includes `ImmunityFilter`.
- Effect movement riders use `SelectStep`(HEX) + `MoveUnitStep`, never `MoveSequenceStep` — EXCEPT Float Like a Butterfly's primary MOVEMENT action, which is exactly what `MoveSequenceStep` is for (standing feedback memory).
- **`hero.deck` is the MASTER card list** — hand/discard cards remain in it; "in the deck" means `card.state == CardState.DECK`. Never call `Hero.return_card_to_deck()` on a card already in the master list (it raises); flip `card.state` manually and remove the card from `hand`/`discard_pile`/`played_cards` slot instead.
- Effect tests live in `tests/engine/effects/cases/` (one file per Task-group, listed per task), use `EffectScenarioBuilder` (`tests/engine/effects/builders.py`) + `run_card` (`tests/engine/effects/runner.py`), marked `@pytest.mark.effect_flow` / `@pytest.mark.effect_contract`. Assert behavior, not wiring. Test basenames unique across `tests/`.
- After EVERY task: `PYTHONPATH=src uv run pytest tests/ -q` passes, plus `uv run ruff check src/ && uv run black --check src/ && uv run mypy src/`.

## File Structure

| File | Responsibility |
|---|---|
| `src/goa2/domain/models/card.py` | `Card.starts_in_deck` field (T1) |
| `src/goa2/domain/models/unit.py` | `initialize_state()` honors the flag (T1) |
| `src/goa2/data/heroes/takahide.py` | set `starts_in_deck=True` on Sting/Strike (T1) |
| `src/goa2/domain/models/effect.py` | `EffectType.EMPTY_HEX_OBSTACLE` (T2) |
| `src/goa2/engine/validation_terrain.py` | empty-hex-obstacle check in `is_obstacle_for_actor` (T2) |
| `src/goa2/domain/models/enums.py` | `StepType.SWAP_WITH_DECK_CARD` (T3) |
| `src/goa2/engine/steps/cards.py` | `SwapWithDeckCardStep` (T3) |
| `src/goa2/engine/steps/__init__.py` | re-export new step (T3) |
| `src/goa2/domain/events.py` | `GameEventType.DECK_CARD_SWAPPED` if nothing existing fits (T3) |
| `src/goa2/domain/views.py` | mask facedown cards outside hand (T4) |
| `src/goa2/engine/steps/selection.py` | exclude facedown cards from DISCARD/PLAYED card enumeration + `include_facedown` opt-in; `color_output_key` (T4, T8) |
| `src/goa2/scripts/takahide_effects.py` | skeleton w/ section markers (T1); all 20 effect classes (T5–T12) |
| `tests/engine/effects/takahide_common.py` | shared `takahide_card()` / `takahide_state()` helpers (T1) |
| `tests/engine/test_takahide_setup.py` | T1 paths |
| `tests/engine/test_empty_hex_obstacle.py` | T2 paths |
| `tests/engine/test_swap_with_deck_card.py` | T3 paths |
| `tests/engine/test_facedown_masking.py` | T4 paths |
| `tests/engine/effects/cases/test_takahide_support.py` | §1–§7 (T5–T7) |
| `tests/engine/effects/cases/test_takahide_discard_punish.py` | §8–§10 (T8) |
| `tests/engine/effects/cases/test_takahide_swap_family.py` | §11–§13 (T9) |
| `tests/engine/effects/cases/test_takahide_denial.py` | §14–§15 (T10) |
| `tests/engine/effects/cases/test_takahide_golds.py` | §16–§20 (T11–T12) |
| `docs/CLIENT_INTEGRATION_GUIDE.md` | facedown masking, new event type (T3/T4) |

## Parallelization & Dependency Graph

```
WAVE 1 (4 parallel lanes — disjoint files, no shared state)
  T1  starts_in_deck + data flags + effects-file skeleton + test helpers
  T2  EMPTY_HEX_OBSTACLE effect type + validator
  T3  SwapWithDeckCardStep
  T4  facedown masking (views + selection)

WAVE 2 (5 parallel lanes — each owns its OWN test file and its OWN
        marked section of scripts/takahide_effects.py)
  Lane A: T5 → T6 → T7   (sequential inside the lane: share _ally_discard_gate)
                          needs T1
  Lane B: T8              needs T1, T4
  Lane C: T9              needs T1
  Lane D: T10             needs T1, T2
  Lane E: T11 → T12       needs T1, T3, T4  (T12 additionally needs T11)

FINAL (after everything)
  T13 coverage cross-check + quality gates + docs
```

**What makes wave 1 safe:** the four tasks touch pairwise-disjoint files (T1: card/unit/data; T2: effect.py/validation_terrain.py; T3: enums.py/steps/cards.py/events.py; T4: views.py/selection.py). Run them as 4 parallel worktree agents or sequentially in any order.

**What constrains wave 2:** repo rule is ONE effects file per hero, so all effect tasks write `scripts/takahide_effects.py`. T1 therefore creates the file up front with one clearly-delimited section marker per lane (`# === Lane A: discard-support families ===` …); each wave-2 lane edits ONLY inside its own section and its own test file, so parallel worktree merges are append-clean. If you instead execute in a single session (subagent-driven), just run wave 2 sequentially in any dependency-respecting order — suggested: T5, T6, T7, T9, T8, T10, T11, T12.

**Not parallelizable:** T6/T7 with T5 (consume `_ally_discard_gate` defined in T5, same file section, same test file); T12 with T11 (post-ultimate fizzle e2e drives T11's effects); T13 with anything.

**Critical path:** T1/T3/T4 → T11 → T12 → T13.

---

### Task 1: `Card.starts_in_deck` + Takahide data flags + shared test helpers + effects-file skeleton (P1, TDD §17 H1 / §18 H1 / §19 H1)

**Files:**
- Modify: `src/goa2/domain/models/card.py` (new field)
- Modify: `src/goa2/domain/models/unit.py` (`initialize_state`, ~line 259)
- Modify: `src/goa2/data/heroes/takahide.py` (flags on `sting_like_a_bee`, `strike_like_a_tiger`)
- Create: `src/goa2/scripts/takahide_effects.py` (imports + lane section markers only)
- Create: `tests/engine/effects/takahide_common.py`
- Test: `tests/engine/test_takahide_setup.py`

**Interfaces:**
- Produces:
  - `Card.starts_in_deck: bool = False` — when True, `Hero.initialize_state()` leaves the card in the deck (`state=DECK`) even if UNTIERED/Tier I.
  - `takahide_common.takahide_card(card_id: str) -> Card` — fresh deep copy from `HeroRegistry.get("hero_takahide")` (search `deck` + `ultimate_card`).
  - `takahide_common.takahide_state(card_id, *, allies=[...], enemies=[...]) -> GameState` — builder-based state with Takahide at origin holding `card_id` as `current_turn_card`, actor set. Signature fixed here; wave-2 lanes import it.
  - `scripts/takahide_effects.py` with module docstring, imports, and five section markers (`# === Lane A/B/C/D/E … ===`) — discovered by `register_all_effects()` even while empty.

- [ ] **Step 1: Write the failing tests** (`tests/engine/test_takahide_setup.py`)

```python
"""P1: starts_in_deck flag + Takahide starting-hand composition."""

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import Card, CardState
from goa2.domain.state import GameState


def fresh_takahide():
    hero = HeroRegistry.get("hero_takahide").model_copy(deep=True)
    hero.initialize_state()
    return hero


def test_starts_in_deck_defaults_false():
    # any existing card factory works; the field just defaults False
    assert Card.model_fields["starts_in_deck"].default is False


def test_takahide_starting_hand_is_five_cards():
    hero = fresh_takahide()
    hand_ids = {c.id for c in hero.hand}
    assert hand_ids == {
        "float_like_a_butterfly", "bushido",
        "proven_warrior", "come_to_aid", "set_an_example",
    }


def test_sting_and_strike_start_in_deck():
    hero = fresh_takahide()
    for cid in ("sting_like_a_bee", "strike_like_a_tiger"):
        card = next(c for c in hero.deck if c.id == cid)
        assert card.state == CardState.DECK


def test_starts_in_deck_survives_serialization():
    hero = fresh_takahide()
    dumped = hero.model_dump_json()
    restored = type(hero).model_validate_json(dumped)
    sting = next(c for c in restored.deck if c.id == "sting_like_a_bee")
    assert sting.starts_in_deck is True
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=src uv run pytest tests/engine/test_takahide_setup.py -q` → FAIL (`starts_in_deck` not a field / hand has 7 cards).
- [ ] **Step 3: Implement** — in `card.py`: `starts_in_deck: bool = False` (plain field, no alias needed). In `unit.py` `initialize_state()`:

```python
for c in self.deck:
    if (c.tier == CardTier.UNTIERED or c.tier == CardTier.I) and not c.starts_in_deck:
        c.state = CardState.HAND
        self.hand.append(c)
    else:
        c.state = CardState.DECK
```

In `takahide.py`: add `starts_in_deck=True` to the Sting/Strike `Card(...)` constructors.
- [ ] **Step 4: Create the effects skeleton + test helper module** (no tests fail on these; they're infrastructure other lanes import). `takahide_state` exemplar:

```python
# tests/engine/effects/takahide_common.py
from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import Card
from tests.engine.effects.builders import EffectScenarioBuilder


def takahide_card(card_id: str) -> Card:
    hero = HeroRegistry.get("hero_takahide")
    for c in list(hero.deck) + ([hero.ultimate_card] if hero.ultimate_card else []):
        if c.id == card_id:
            return c.model_copy(deep=True)
    raise LookupError(card_id)


def takahide_state(card_id: str, *, allies=(), enemies=((3, 0, -3),)):
    """Takahide (RED) at origin with `card_id` committed; allies/enemies are
    coordinate tuples; ally ids are hero_ally_1.., enemy ids hero_enemy_1.."""
    b = EffectScenarioBuilder().small_arena().red_hero(
        "hero_takahide", at=(0, 0, 0), current_card=takahide_card(card_id)
    )
    for i, at in enumerate(allies, 1):
        b = b.red_hero(f"hero_ally_{i}", at=at)
    for i, at in enumerate(enemies, 1):
        b = b.blue_hero(f"hero_enemy_{i}", at=at)
    return b.with_actor("hero_takahide").build()
```

(Adapt the builder-method names to the actual `EffectScenarioBuilder` API if they differ — read `builders.py` first. Ally/enemy heroes need real decks only where a test manipulates their hand/discard: set `state.get_hero(...).hand`/`discard_pile` directly in those tests.)
- [ ] **Step 5: Run** — new tests + full suite pass.
- [ ] **Step 6: Commit** — `feat: starts_in_deck card flag; Takahide setup + effect scaffolding`

---

### Task 2: `EMPTY_HEX_OBSTACLE` effect type + validator integration (P4, S8 backbone)

**Files:**
- Modify: `src/goa2/domain/models/effect.py` (enum value + docstring)
- Modify: `src/goa2/engine/validation_terrain.py` (`is_obstacle_for_actor`, ~line 29)
- Test: `tests/engine/test_empty_hex_obstacle.py`

**Interfaces:**
- Produces: `EffectType.EMPTY_HEX_OBSTACLE = "empty_hex_obstacle"`. Semantics consumed by T10: an ACTIVE effect of this type with `scope=EffectScope(shape=RADIUS, range=N, origin_id=<source hero>, affects=ENEMY_UNITS)` makes any EMPTY hex within raw cube distance N of the source's CURRENT position an obstacle for units on a team different from the source's team (heroes AND minions — interp 14). Occupied/terrain hexes unaffected (already obstacles or handled by occupancy).
- Consumes: nothing new.

Implementation notes (read `validation_terrain.py` fully first):
- The existing early return for non-hero actors (line ~65) guards STATIC_BARRIER only — restructure so `EMPTY_HEX_OBSTACLE` is evaluated for ANY unit actor (minions included). Resolve the actor's team via `state.get_entity(...)`; resolve the source team via the effect's `source_id` hero.
- Distance = raw cube distance (`Hex.distance`) from `state.get_position(effect.scope.origin_id)` — NOT topology (would recurse into obstacle definitions; same reason Wasp's barrier uses raw distance). Dynamic origin (interp 12) falls out of reading the position at check time.
- "Empty" = the tile at `hex_pos` has no occupant and no terrain — at this point in the function `tile.is_obstacle` was already False, so every hex reaching the check is empty by definition; assert that assumption in a comment.
- Respect `effect.is_active` (created dormant, activated at turn finalization) and skip when the acting unit's team equals the source hero's team.

- [ ] **Step 1: Write the failing tests** — build a state (plain `EffectScenarioBuilder`), append an `ActiveEffect` to `state.active_effects` by hand:

```python
import pytest

from goa2.domain.hex import Hex
from goa2.domain.models.effect import (
    ActiveEffect, AffectsFilter, DurationType, EffectScope, EffectType, Shape,
)
from tests.engine.effects.builders import EffectScenarioBuilder


def _denial_state(radius: int = 1):
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_takahide", at=(0, 0, 0))
        .red_hero("hero_ally_1", at=(0, 2, -2))
        .blue_hero("hero_enemy_1", at=(3, 0, -3))
        .blue_minion("minion_e1", at=(3, -1, -2))
        .with_actor("hero_enemy_1")
        .build()
    )
    state.active_effects.append(ActiveEffect(
        id="fx_denial", source_id="hero_takahide",
        effect_type=EffectType.EMPTY_HEX_OBSTACLE,
        scope=EffectScope(shape=Shape.RADIUS, range=radius,
                          origin_id="hero_takahide",
                          affects=AffectsFilter.ENEMY_UNITS),
        duration=DurationType.THIS_TURN,
        created_at_turn=state.turn, created_at_round=state.round,
        is_active=True,
    ))
    return state


def test_empty_adjacent_hex_is_obstacle_for_enemy_hero():
    state = _denial_state()
    adj = Hex(q=1, r=0, s=-1)  # empty, adjacent to Takahide
    assert state.validator.is_obstacle_for_actor(state, adj, "hero_enemy_1")


def test_same_hex_is_not_obstacle_for_friendly_unit():
    state = _denial_state()
    assert not state.validator.is_obstacle_for_actor(state, Hex(q=1, r=0, s=-1), "hero_ally_1")


def test_enemy_minion_actor_is_blocked_too():
    state = _denial_state()
    assert state.validator.is_obstacle_for_actor(state, Hex(q=1, r=0, s=-1), "minion_e1")


def test_inactive_effect_does_nothing():
    state = _denial_state()
    state.active_effects[-1].is_active = False
    assert not state.validator.is_obstacle_for_actor(state, Hex(q=1, r=0, s=-1), "hero_enemy_1")


def test_dynamic_origin_follows_source_position():
    state = _denial_state()
    # move Takahide 2 hexes; old ring frees up, new ring is denied
    from goa2.domain.types import BoardEntityID
    state.entity_locations[BoardEntityID("hero_takahide")] = Hex(q=-2, r=0, s=2)
    assert not state.validator.is_obstacle_for_actor(state, Hex(q=1, r=0, s=-1), "hero_enemy_1")
    assert state.validator.is_obstacle_for_actor(state, Hex(q=-1, r=0, s=1), "hero_enemy_1")
```

(Also add: hex OUTSIDE radius not blocked; radius=2 blocks at distance 2. Use `state.set_position`/the builder's placement mechanism instead of writing `entity_locations` directly if a setter exists — read `state.py` first.)
- [ ] **Step 2: Verify failure** — enum value missing → `AttributeError`.
- [ ] **Step 3: Implement** enum + validator branch.
- [ ] **Step 4: Run** — new tests + full suite (Wasp tests must stay green).
- [ ] **Step 5: Commit** — `feat: EMPTY_HEX_OBSTACLE effect type (actor-conditional empty-hex denial)`

---

### Task 3: `SwapWithDeckCardStep` (P2, S9)

**Files:**
- Modify: `src/goa2/domain/models/enums.py` (`StepType.SWAP_WITH_DECK_CARD = "swap_with_deck_card"`)
- Modify: `src/goa2/engine/steps/cards.py` (new step, next to `SwapCardStep` ~line 972)
- Modify: `src/goa2/engine/steps/__init__.py` (re-export)
- Modify: `src/goa2/domain/events.py` — check `GameEventType` for a fitting card-movement event; if none, add `DECK_CARD_SWAPPED = "deck_card_swapped"` (then also note it in `docs/CLIENT_INTEGRATION_GUIDE.md`)
- Test: `tests/engine/test_swap_with_deck_card.py`

**Interfaces:**
- Produces: `SwapWithDeckCardStep(GameStep)` with fields:
  - `hero_id: str | None = None`, `hero_key: str | None = None` (owner; falls back to `current_actor_id`)
  - `outgoing_card_id: str | None = None`, `outgoing_card_key: str | None = None` (the card leaving play; found in hand / discard_pile / played_cards slot / current_turn_card)
  - `incoming_card_key: str = "deck_swap_card"` (context key holding the chosen DECK-state card id)
  - `facedown_if_from_discard_or_resolved: bool = False` (Bushido rider)
  - honors `active_if_key`/`skip_if_key` (`should_skip`)
- Semantics: incoming card inherits the outgoing card's exact location AND `state`/`is_facedown`/`played_this_round` (facedown forced True when the rider flag is set and the outgoing card was in `discard_pile` or a `played_cards` slot). Outgoing card: `state=DECK`, `is_facedown=False`, `played_this_round=False`, removed from its container/field (do NOT call `return_card_to_deck` — master-list constraint, see Global Constraints; just clear the reference). Both cards' active effects expire via `EffectManager.expire_by_card`. Emits the swap `GameEvent` with both card ids. No-ops cleanly (finished, no event) when either card can't be found or the incoming card isn't `state == DECK`.

- [ ] **Step 1: Write the failing tests.** Build a minimal hero (reuse `takahide_common` if T1 landed; otherwise a hand-built `Hero` with 3 gold `Card`s — the step is hero-agnostic, don't couple to Takahide data). Cover: swap from HAND (incoming faceup HAND); swap from DISCARD with rider → incoming in `discard_pile` with `state == CardState.DISCARD` and `is_facedown is True`; swap from a `played_cards` slot with rider → incoming occupies the same index, facedown, `state == RESOLVED`; swap from `current_turn_card` (no rider) → incoming becomes the turn card faceup; outgoing always ends `state == DECK`, faceup, `played_this_round False`, absent from hand/discard/slots; effects with `source_card_id` of either card get expired (append a dummy `ActiveEffect`, assert inactive/removed — mirror how `SwapCardStep` tests assert this, grep `expire_by_card` in `tests/`); missing incoming id → clean no-op; incoming card not in DECK state → clean no-op.

```python
def test_swap_from_discard_places_incoming_facedown():
    hero = make_hero_with_golds()          # gold_a in discard, gold_b + gold_c state DECK
    state = state_with(hero)               # tiny helper, no board needed beyond registration
    state.execution_context["deck_swap_card"] = "gold_b"
    step = SwapWithDeckCardStep(
        hero_id=str(hero.id), outgoing_card_id="gold_a",
        facedown_if_from_discard_or_resolved=True,
    )
    result = step.resolve(state, state.execution_context)
    assert result.is_finished
    gold_a = find(hero, "gold_a"); gold_b = find(hero, "gold_b")
    assert gold_b in hero.discard_pile and gold_b.state == CardState.DISCARD
    assert gold_b.is_facedown is True
    assert gold_a not in hero.discard_pile and gold_a.state == CardState.DECK
    assert gold_a.is_facedown is False
```

- [ ] **Step 2: Verify failure** (`StepType` missing → import error).
- [ ] **Step 3: Implement** (model the container bookkeeping on `SwapItemCardStep` at `cards.py:1047`, which already does replace-in-place across hand/discard/current/played).
- [ ] **Step 4: Run** — new tests + full suite.
- [ ] **Step 5: Commit** — `feat: SwapWithDeckCardStep for deck-card exchanges`

---

### Task 4: Facedown-outside-hand masking (P3, S13, interp 2)

**Files:**
- Modify: `src/goa2/domain/views.py` (discard/played card serialization)
- Modify: `src/goa2/engine/steps/selection.py` (card enumeration for DISCARD/PLAYED containers; new opt-in field)
- Modify: `docs/CLIENT_INTEGRATION_GUIDE.md` (facedown cards can now appear in discard/resolved areas; masked shape)
- Test: `tests/engine/test_facedown_masking.py`

**Interfaces:**
- Produces:
  - `build_view()`: a card with `is_facedown=True` in `discard_pile` or `played_cards` renders masked for ALL viewers including the owner (same masked shape already used for opponents' facedown committed cards — find and reuse that masking helper in `views.py`; identity fields hidden, `is_facedown: true` present so clients can render a card back).
  - `SelectStep` (CARD target type): when enumerating `CardContainerType.DISCARD` / `PLAYED`, facedown cards are EXCLUDED by default; new field `include_facedown: bool = False` opts back in (consumed by T6's retrieve — S15).
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests** — build a two-hero state; put a card in hero A's discard with `is_facedown=True` (set fields directly); assert:
  - owner view, opponent view, and spectator view (`for_hero_id=None`) all mask identity (no `id`/`name`/`color` of the real card — match the exact masked shape used for facedown committed cards; read `views.py` first and pin the same keys),
  - a faceup discard card still renders fully,
  - a `SelectStep(CARD, card_container=DISCARD)` enumeration offers only the faceup card; with `include_facedown=True` it offers both (drive via the step's `resolve` and inspect the emitted `InputRequest` options).
- [ ] **Step 2: Verify failure** (facedown discard renders its real id today).
- [ ] **Step 3: Implement** both changes.
- [ ] **Step 4: Run** — new tests + full suite (`tests/server/` too — views are client contract).
- [ ] **Step 5: Update the client guide** (facedown-in-discard/resolved masking; `include_facedown` is server-internal, don't document it).
- [ ] **Step 6: Commit** — `feat: mask facedown cards outside hand in views and card selection`

---

### Task 5: `_ally_discard_gate` + Come to Aid / Bring the Relief / Commit Reserves (TDD §1–§3, S1, S2)

**Files:**
- Modify: `src/goa2/scripts/takahide_effects.py` (Lane A section)
- Test: `tests/engine/effects/cases/test_takahide_support.py` (new file; §1 H1–H4/U1–U5, §2, §3)

**Interfaces:**
- Produces:
  - `_ally_discard_gate(hero, distance, *, attack_cards_only=False) -> list[GameStep]` — module-level helper writing context keys **`tk_ally`** (chosen ally id), **`tk_has_discard`** (truthy flag). Steps: `SelectStep(UNIT, output_key="tk_ally", is_mandatory=True, filters=[TeamFilter(FRIENDLY), <hero-unit filter>, RangeFilter(max_range=distance), <exclude-self filter>, ImmunityFilter()])` → `SelectStep(CARD, card_container=HAND, context_hero_id_key="tk_ally", override_player_id_key="tk_ally", output_key="tk_ally_discard", is_mandatory=False, active_if_key="tk_ally")` → `DiscardCardStep(card_key="tk_ally_discard", hero_key="tk_ally", active_if_key="tk_ally_discard")` → `CountCardsStep(hero_key="tk_ally", card_container=DISCARD, output_key="tk_ally_discard_count")` → `CheckContextConditionStep(input_key="tk_ally_discard_count", operator=">=", threshold=1, output_key="tk_has_discard")`. (Brogan Throwing Spear pattern, `brogan_effects.py:556` — read it first; use the exact filter classes existing scripts use for "friendly hero, not self, not immune" — grep `ExcludeIdentityFilter`/`exclude_self` and `UnitTypeFilter` usages.) Mandatory first select + no ally ⇒ whole action aborts, which IS §1 U1's "fizzles entirely".
  - `attack_cards_only=True`: the hand select restricted to `primary_action == ATTACK` — check `SelectStep` for an existing card-action filter param; if none, add `card_primary_actions: list[ActionType] | None = None` to `SelectStep` (field only, no new type; used by T7).
  - `SupportMoveEffect` registered for `come_to_aid` (move 3), `bring_the_relief` (move 4), `commit_reserves` (move 4, `ignore_obstacles=True`) — gate + optional Takahide move rider `active_if_key="tk_has_discard"`.
- Consumes: `takahide_common` (T1). The optional-move rider = `SelectStep`(HEX, reachable within N by topology, optional) + `MoveUnitStep` — copy the canonical optional-move pattern from an existing script (grep `MoveUnitStep(` in `scripts/`; `docs/EFFECT_AUTHOR_REFERENCE.md` names the reachable-hex filter); pass the ignore-obstacles flag the same way that pattern's pathing does for Commit Reserves.

- [ ] **Step 1: Write the failing tests** — every §1 H/U path, then §2/§3 deltas. Exemplars (§1 H1, H2):

```python
import pytest

from goa2.domain.models import CardState
from tests.engine.effects.runner import run_card
from tests.engine.effects.takahide_common import takahide_state


@pytest.mark.effect_flow
def test_come_to_aid_h1_ally_discards_then_takahide_moves():
    state = takahide_state("come_to_aid", allies=[(0, 2, -2)])
    ally = state.get_hero("hero_ally_1")
    give_hand(ally, n=2)                       # file-local helper: real Card objects, state HAND
    run = run_card(state, "hero_takahide")
    run.expect_input("SELECT_UNIT").choose("hero_ally_1")
    run.expect_input("SELECT_CARD").choose(ally.hand[0].id)   # routed to ally's player — assert player_id
    run.expect_input("SELECT_HEX").choose({"q": 1, "r": 0, "s": -1})
    run.finish()
    assert len(ally.discard_pile) == 1
    assert state.get_position("hero_takahide") == hex_at((1, 0, -1))


@pytest.mark.effect_flow
def test_come_to_aid_h2_decline_with_preexisting_discard_still_moves():
    state = takahide_state("come_to_aid", allies=[(0, 2, -2)])
    ally = state.get_hero("hero_ally_1")
    give_discard(ally, n=1)                    # pre-existing discard, hand present
    give_hand(ally, n=1)
    run = run_card(state, "hero_takahide")
    run.expect_input("SELECT_UNIT").choose("hero_ally_1")
    run.expect_input("SELECT_CARD").skip()
    run.expect_input("SELECT_HEX")             # move still offered
```

(Assert the discard prompt's `player_id` is the ally's — §1 H4/S1. §1 U4 topology test: wall of terrain between Takahide and the ally, raw distance 3 but path 5 → ally not offered.)
- [ ] **Step 2: Verify failure** (effects unregistered → card resolves with no prompts).
- [ ] **Step 3: Implement** helper + `SupportMoveEffect`.
- [ ] **Step 4: Run** — file + full suite.
- [ ] **Step 5: Commit** — `feat: Takahide discard-support movement family`

---

### Task 6: Pledge of Allegiance / Loyal Retainer (TDD §4–§5, S15, S17)

**Files:**
- Modify: `src/goa2/scripts/takahide_effects.py` (Lane A section)
- Test: `tests/engine/effects/cases/test_takahide_support.py` (append §4–§5)

**Interfaces:**
- Produces: `SupportEconomyEffect` registered for `pledge_of_allegiance` (1 coin) / `loyal_retainer` (2 coins).
- Consumes: `_ally_discard_gate` (T5), `GainCoinsStep(hero_key=..., amount=..., active_if_key="tk_has_discard")`, `SetContextFlagStep(key="tk_self", value=hero.id)` (so `GainCoinsStep(hero_key="tk_self")` pays Takahide — it has no literal-id field), `RetrieveCardStep(card_key="tk_retrieve", ...)` behind an optional `SelectStep(CARD, card_container=DISCARD, include_facedown=True, output_key="tk_retrieve", is_mandatory=False, active_if_key="tk_has_discard")` over Takahide's OWN discard (interp 7; `include_facedown=True` per S15 — needs T4 only for the flag to exist; if running before T4 lands, mark that one test `xfail` and un-xfail in T13).

- [ ] **Step 1: Failing tests** — §4 H1–H4/U1–U3, §5 H1. For §4 H1 assert BOTH `hero.gold` deltas (+1 each) and the retrieved card back in Takahide's hand. For §4 U3: the ally's just-discarded card is not among the retrieve options (inspect the `InputRequest` options list). For §4 H4: seed Takahide's discard with a facedown card and assert it's offered and returns to hand faceup.
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Takahide coin/retrieve support family`

---

### Task 7: Calculated Risk / Tactical Gambit (TDD §6–§7, S2, S3)

**Files:**
- Modify: `src/goa2/scripts/takahide_effects.py` (Lane A section)
- Test: `tests/engine/effects/cases/test_takahide_support.py` (append §6–§7)

**Interfaces:**
- Produces: `SupportRepositionEffect` registered for `calculated_risk` / `tactical_gambit` (`ignore_obstacles=True`).
- Consumes: `_ally_discard_gate(hero, stats.radius, attack_cards_only=True)` (T5) — radius card, so distance = `stats.radius`; then the ALLY's optional move up to 2: same optional-move assembly as T5 but `MoveUnitStep` target = `tk_ally` and BOTH the hex select and the accept/decline route to the ally (`override_player_id_key="tk_ally"`), `active_if_key="tk_has_discard"`.

- [ ] **Step 1: Failing tests** — §6 H1–H3/U1–U3, §7 H1/U1. §6 H3 is the load-bearing one: ally's hand = one ATTACK-primary card + one SKILL-primary card → the discard prompt offers ONLY the attack card. §6 H2: pre-existing discard may be ANY card (seed a skill card in discard, empty-ish hand) → move still offered.
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Takahide ally reposition family`

---

### Task 8: Proven Warrior / Chosen Champion / The Right Hand (TDD §8–§10, S4, S5)

**Files:**
- Modify: `src/goa2/engine/steps/selection.py` (`SelectStep.color_output_key: str | None = None` — when set and a CARD is selected, also writes the card's `color.value` to that context key)
- Modify: `src/goa2/scripts/takahide_effects.py` (Lane B section)
- Test: `tests/engine/effects/cases/test_takahide_discard_punish.py` (new file; §8 all, §9 H1, §10 all)

**Interfaces:**
- Produces: `DiscardPunishEffect` registered for `proven_warrior` / `chosen_champion` / `the_right_hand` (`max_victims=2`, optional picks).
- Consumes: `ForceDiscardByColorStep(victim_key=..., color_key="tk_color")` (existing, `cards.py:401`), T4's default faceup-only card enumeration (§8 U5).

Assembly:
1. `SelectStep(UNIT, output_key="tk_discard_owner", is_mandatory=True, filters=[TeamFilter(FRIENDLY), <hero-unit>, RangeFilter(max_range=stats.radius), <exclude-self>, ImmunityFilter()])` — but candidates must ALSO have a non-empty, non-all-facedown discard, or the mandatory pick strands the action on a dead choice; grep filters for a has-discard/card-count filter (a `CardCountFilter`-like exists near `filters_cards.py:116`) and include it; if none fits, filter at build time is NOT possible (radius is runtime) — add the smallest filter reusing that count logic.
2. `SelectStep(CARD, card_container=DISCARD, context_hero_id_key="tk_discard_owner", output_key="tk_color_card", color_output_key="tk_color", is_mandatory=True)` — chooser defaults to Takahide (no override key): S4.
3. Victims: Proven Warrior/Chosen Champion: ONE mandatory `SelectStep(UNIT, output_key="tk_victim_1", filters=[TeamFilter(ENEMY), <hero-unit>, RangeFilter(max_range=stats.radius), ImmunityFilter()])` + `ForceDiscardByColorStep(victim_key="tk_victim_1", color_key="tk_color")`. Mandatory-with-no-candidates would abort — that contradicts §8 U3 ("color chosen but nothing happens"), so the victim select must be assembled only when… you cannot know at build time (radius is runtime): make the victim select `is_mandatory=False` and rely on the rules-mandatory convention being satisfied by prompting — CHECK how existing "an enemy hero in radius discards" effects handle this exact abort-vs-fizzle tension (Snorri Runetrap, `snorri_effects.py`) and copy that choice; note the resolution in the test file docstring.
4. The Right Hand: two selects, each `is_mandatory=False` (interp 9: freely 0/1/2), second one excluding `tk_victim_1` (grep for the exclude-by-context-key filter used by repeat attacks — Snorri Sigils/Silverarrow precedent), each followed by its `ForceDiscardByColorStep`.

- [ ] **Step 1: Failing tests** — all §8 paths (incl. U5: seed a facedown card in the ally's discard → not among the color-source options; U1: victim with no matching color → no discard event, hand unchanged; H2: GOLD source card forces a gold discard), §9 H1 at radius 4, §10 H1/H2/U1/U2.
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Takahide color-discard punish family`

---

### Task 9: Set an Example / Lead from the Front / Hold My Saké (TDD §11–§13, S6, S7)

**Files:**
- Modify: `src/goa2/scripts/takahide_effects.py` (Lane C section)
- Test: `tests/engine/effects/cases/test_takahide_swap_family.py` (new file; §11 all, §12 H1, §13 all)

**Interfaces:**
- Produces: `UnresolvedSwapEffect` registered for `set_an_example` / `lead_from_the_front` / `hold_my_sake` (`allow_discard_source=True`).
- Consumes: `AttackSequenceStep(damage=stats.primary_value, range_val=1)` (adjacent attack — copy the exact adjacent-attack assembly incl. `is_ranged` handling from an existing melee RED card, e.g. tigerclaw/brogan), `HasUnresolvedCardFilter` (`filters_cards.py:21`), `SwapCardStep(target_card_key="tk_swap_card", context_hero_id_key="tk_swap_hero")` (source defaults to that hero's `current_turn_card` — exactly what we want), T5-style routing.

Assembly after the attack: `SelectStep(UNIT, output_key="tk_swap_hero", is_mandatory=False, filters=[TeamFilter(FRIENDLY), <hero-unit>, RangeFilter(max_range=stats.radius), <exclude-self>, ImmunityFilter(), HasUnresolvedCardFilter()])` → `SelectStep(CARD, output_key="tk_swap_card", is_mandatory=False, context_hero_id_key="tk_swap_hero", override_player_id_key="tk_swap_hero", active_if_key="tk_swap_hero", card_container=HAND)` — Hold My Saké instead passes both containers (`card_containers=[HAND, DISCARD]`, faceup-only default handles §13 U2) → `SwapCardStep(..., active_if_key="tk_swap_card")`.

Test-state note: the swapped ally needs `current_turn_card` with `state=UNRESOLVED`, `is_facedown=False` (Resolution phase = revealed, interp 10) and must be in `state.unresolved_hero_ids` — use the builder's `with_unresolved_heroes([...])` + `with_card(ally_id, card)` then set the card's state/facedown explicitly.

- [ ] **Step 1: Failing tests** — every §11 path. §11 H2 (dynamic initiative) is a flow test: after the swap, `run.finish()` the turn with `finalize_turn=True`, then assert `resolve_next_action` picks the ally when the swapped-in card's initiative beats the other unresolved hero's, and doesn't when it's lower (two scenarios). §11 H3: attach a defending enemy that blocks the attack → rider still prompts. §13 H1: swap with a discard card → old turn card in `discard_pile`, faceup, `state == DISCARD`; incoming from discard is the UNRESOLVED faceup turn card.
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Takahide unresolved-card swap family`

---

### Task 10: Spinning Blade / Blade Helix (TDD §14–§15, S8)

**Files:**
- Modify: `src/goa2/scripts/takahide_effects.py` (Lane D section)
- Test: `tests/engine/effects/cases/test_takahide_denial.py` (new file; §14 all, §15 all)

**Interfaces:**
- Produces: `SpatialDenialEffect` registered for `spinning_blade` (radius literal 1) / `blade_helix` (radius = `stats.radius`).
- Consumes: T2's `EMPTY_HEX_OBSTACLE`; `CreateEffectStep(effect_type=EffectType.EMPTY_HEX_OBSTACLE, scope=EffectScope(shape=Shape.RADIUS, range=<radius>, origin_id=hero.id, affects=AffectsFilter.ENEMY_UNITS), duration=DurationType.THIS_TURN)` after the adjacent `AttackSequenceStep` (same adjacent-attack assembly as T9). Default `CreateEffectStep` card-binding + dormant `is_active` is correct: `FinalizeHeroTurnStep` activates it (S8).

- [ ] **Step 1: Failing tests** — behavior-level, driving `run_card(..., finalize_turn=True)`:
  - §14 H1: after Takahide's turn finalizes, `state.validator.is_obstacle_for_actor(state, <empty adjacent hex>, "hero_enemy_1")` is True (and a `MoveUnitStep`/pathing attempt for the enemy through that hex fails — pick whichever the existing Wasp barrier tests assert and mirror them, grep `STATIC_BARRIER` in `tests/`).
  - §14 H2: `rules` distance/path for the enemy to a hex behind the ring is longer than for an ally (topology impact).
  - §14 H3 minion actor blocked; H4 friendly free; H5 dynamic (move Takahide's position, re-assert); H7 defended attack still creates the effect.
  - §14 U1 expiry: advance end-of-turn (drive the same end-of-turn path the Wasp THIS_TURN tests use) → check the effect is expired/inactive.
  - §14 U2: no adjacent target → aborted action → `state.active_effects` has no denial effect.
  - §15 H2: set `hero.items[StatType.RADIUS] = 1` before building steps → denial radius 2 (assert a distance-2 empty hex blocks).
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Takahide spatial denial family`

---

### Task 11: Gold cycle — Float / Sting / Strike + Bushido (TDD §16–§19, S9, S10, S11, S14)

**Files:**
- Modify: `src/goa2/scripts/takahide_effects.py` (Lane E section)
- Test: `tests/engine/effects/cases/test_takahide_golds.py` (new file; §16 all, §17 all, §18 all, §19 all — EXCEPT the post-ultimate paths §17 U1/§18 U2, which are exercised end-to-end in T12; here they're covered by the build-time "no deck golds → no swap steps" unit angle: empty the deck golds manually)
- Test helper: `_gold_swap_steps` is internal; tests stay behavioral.

**Interfaces:**
- Produces:
  - `_gold_swap_steps(hero, *, facedown_rider=False, outgoing_card_id) -> list[GameStep]`: at build time, `deck_golds = [c for c in hero.deck if c.color == CardColor.GOLD and c.state == CardState.DECK]`; empty → `[]` (post-ultimate fizzle, interp 1; safe because the own deck cannot change mid-action); else `SelectStep(CARD, card_container=DECK, card_colors=[CardColor.GOLD], output_key="deck_swap_card", is_mandatory=True)` + `SwapWithDeckCardStep(hero_id=hero.id, outgoing_card_id=outgoing_card_id, facedown_if_from_discard_or_resolved=facedown_rider)`. CHECK first that `SelectStep` enumerates `CardContainerType.DECK` (it counts it in `CountCardsStep`; if the selector lacks DECK support, add it — enumeration only, faceup, owner-visible).
  - `FloatEffect` (`float_like_a_butterfly`): `MoveSequenceStep(range_val=stats.primary_value)` (primary MOVEMENT action — the one legitimate `MoveSequenceStep` use) + `_gold_swap_steps(hero, outgoing_card_id=card.id)`.
  - `StingEffect` (`sting_like_a_bee`): `SelectStep(UNIT, filters=[TeamFilter(ENEMY), RangeFilter(min_range=r, max_range=r), ImmunityFilter()], is_mandatory=True, output_key="target_id")` with `r = stats.range` (S14, exact max range) + `AttackSequenceStep(damage=stats.primary_value, range_val=r, is_ranged=True, target_id_key="target_id")` + swap steps.
  - `StrikeEffect` (`strike_like_a_tiger`): adjacent `AttackSequenceStep(damage=stats.primary_value, range_val=1)` + swap steps.
  - `BushidoEffect` (`bushido`): locate at build time the single gold outside the deck — `next(c for c in hero.deck if c.color == CardColor.GOLD and c.state != CardState.DECK)` (S11; pre-ultimate invariant guarantees exactly one; if none — post-ultimate can't happen since Bushido is then in the deck, but guard with a clean no-op) — then `_gold_swap_steps(hero, facedown_rider=True, outgoing_card_id=<that card>.id)`.
- Consumes: T1 (setup/flags), T3 (`SwapWithDeckCardStep`), T4 (masking asserted in §16 H4).

- [ ] **Step 1: Failing tests** — exemplar (§17 H2):

```python
@pytest.mark.effect_flow
def test_float_h2_move_then_swap_into_resolved_slot():
    state = takahide_state("float_like_a_butterfly")
    taka = state.get_hero("hero_takahide")
    run = run_card(state, "hero_takahide", finalize_turn=True)
    run.expect_input("SELECT_HEX").choose({"q": 2, "r": 0, "s": -2})   # movement (adapt to MoveSequenceStep prompts)
    run.expect_input("SELECT_CARD").choose("sting_like_a_bee")          # which deck gold
    run.finish()
    float_card = next(c for c in taka.deck if c.id == "float_like_a_butterfly")
    sting = next(c for c in taka.deck if c.id == "sting_like_a_bee")
    assert float_card.state == CardState.DECK and float_card.is_facedown is False
    assert sting.state == CardState.RESOLVED and sting.is_facedown is False
    assert taka.played_cards[0] is sting
```

Cover: §16 H1 (hand gold, incoming faceup in hand), H2/H3 (facedown into slot/discard), H4 (opponent view masks it — one `build_view` assertion), H5 (end-of-round `retrieve_cards()` → faceup in hand), H6 (no outgoing prompt: first input is already the deck-gold pick), U2 (only choice is which gold); §17 H3 (0-space move still swaps — mandatory), H4 (end-of-round: swapped-in gold in hand), U1-variant (strip deck golds → no swap prompt, Float resolves in place), U2 (a Tier II deck card and the silver are not offered in the swap options); §18 H2 (exact-max-range: unit at range 2 of 3 NOT targetable), H3/H4, U1 (no unit at max range → abort → sting still in hand, no swap); §19 H2/U1.
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Takahide gold cycle (Float/Sting/Strike, Bushido)`

---

### Task 12: Ready for War ultimate (TDD §20, S16, P5)

**Files:**
- Modify: `src/goa2/scripts/takahide_effects.py` (Lane E section)
- Test: `tests/engine/effects/cases/test_takahide_golds.py` (append §20)

**Interfaces:**
- Produces: `ReadyForWarEffect` registered for `ready_for_war`, implementing `on_ultimate_unlocked(self, state: GameState, hero: Hero) -> None` (hook already called from `engine/steps/phases.py:~203` at level-8; Ursafar `ursafar_effects.py:756` is the template — read it first for signature and event emission style). Logic:
  1. Find the SILVER card (`c.color == CardColor.SILVER` in `hero.deck` master list). If already `state == DECK` → return (idempotence, §20 U1).
  2. Remove it from wherever it lives: `hero.hand.remove` / `hero.discard_pile.remove` / null its `played_cards` slot / clear `current_turn_card`; set `state = CardState.DECK`, `is_facedown = False`, `played_this_round = False`. (Manual — master-list constraint.)
  3. For each gold with `state == CardState.DECK`: `hero.return_card_to_hand(card)` (safe: not in `hand`).
  4. Emit `GameEvent`s (reuse `CARD_RETRIEVED` for the golds and the T3 swap/deck event for the silver — match whatever T3 settled on; metadata includes card ids and `"source": "ready_for_war"`).
- Consumes: T11's effects (for §20 H7's e2e fizzle).

- [ ] **Step 1: Failing tests** — §20 H1 (silver in hand → deck; hand == 6; both golds arrived), H2 (silver seeded in discard), H3 (silver seeded in a played slot → slot becomes `None`), H4 (works whichever two golds are in the deck — seed Float in discard, Sting as the out-of-deck gold's inverse, assert the two DECK ones moved), H5 (events emitted), H6 (`retrieve_cards()` after → silver still DECK, hand back to 6), H7 (full `run_card` of Float post-ultimate → movement prompt, NO card-swap prompt, Float ends RESOLVED in its slot), U1 (calling `on_ultimate_unlocked` twice → second call no-op). Drive the hook directly (`effect.on_ultimate_unlocked(state, hero)`) for most paths + ONE integration through the level-up path if Ursafar's tests show a harness for it (mirror them; if they also call the hook directly, do the same and note it).
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Takahide Ready for War ultimate`

---

### Task 13: Final sweep — coverage cross-check, quality gates, docs

**Files:**
- Modify: `docs/superpowers/plans/2026-07-11-takahide-tdd-paths.md` (status header → IMPLEMENTED)
- Modify: `docs/CLIENT_INTEGRATION_GUIDE.md` (verify T3/T4 additions landed)

- [ ] **Step 1:** `PYTHONPATH=src uv run pytest tests/ -q` — everything green.
- [ ] **Step 2:** `uv run ruff check src/ && uv run black src/ && uv run mypy src/` — clean.
- [ ] **Step 3:** Cross-check every H/U path in the TDD doc has a matching test (grep test names per section §1–§20); add any missed; resolve any `xfail` left by T6.
- [ ] **Step 4:** Update the TDD doc status header; verify the client guide documents facedown masking + any new event type.
- [ ] **Step 5: Commit** — `docs: mark Takahide implemented; client guide updates`

---

## Self-Review Notes

- **Spec coverage:** §1–3→T5, §4–5→T6, §6–7→T7, §8–10→T8, §11–13→T9, §14–15→T10, §16–19→T11, §20→T12; P1→T1, P2→T3, P3→T4, P4→T2, P5→T12; S1/S2→T5, S3→T7, S4/S5→T8, S6/S7→T9, S8→T2+T10, S9/S10/S11→T11 (T3 mechanics), S12→T1, S13→T4, S14→T11, S15→T6, S16→T12, S17→T6. All covered.
- **Type consistency:** context keys fixed across tasks: `tk_ally`, `tk_ally_discard`, `tk_ally_discard_count`, `tk_has_discard` (T5, consumed T6/T7); `tk_color` via `color_output_key` (T8); `tk_swap_hero`/`tk_swap_card` (T9); `deck_swap_card` (T3 default, consumed T11). `SwapWithDeckCardStep` field names in T3 match T11's usage. `takahide_state(card_id, *, allies, enemies)` defined T1, consumed T5–T12.
- **Known judgment calls for implementers** (each task says read-the-named-file-first): exact friendly-hero/exclude-self filter classes (T5), reachable-hex optional-move pattern (T5/T7), mandatory-vs-fizzle for the victim select (T8 — copy Snorri Runetrap's resolution), `SelectStep` DECK-container support (T11), Ursafar unlock-test harness (T12), which existing `GameEventType` fits deck swaps (T3).
