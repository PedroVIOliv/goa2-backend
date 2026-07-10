# Snorri Rune Hero Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Snorri's 16 card effects + Rune Mastery ultimate on top of a new persistent rune-marker system (`Hero.rune_slots`), fully TDD per the approved paths doc.

**Architecture:** Runes are stored as a new `Hero.rune_slots: dict[int, RuneType]` field (persists across rounds and defeat for free; public in views). A single helper `active_runes()` in `scripts/snorri_effects.py` computes the active set from `state.turn` plus the ultimate's per-action/per-defense context keys. Effects are 9 classes (6 tier families + Inscribe + Rune Sigils + ultimate) assembled from existing steps; new primitives: `PlaceRunesStep`, `ChooseRuneStep`, `attack_is_basic` context flag, `SnapshotAdjacentHeroesStep`, `SwapItemCardStep`, `PassiveTrigger.BEFORE_DEFENSE`.

**Tech Stack:** Python 3.11+, Pydantic V2, pytest. Run tests: `PYTHONPATH=src uv run pytest tests/ -q`.

## Global Constraints

- **REQUIRED READING before any task:** `docs/superpowers/plans/2026-07-10-snorri-tdd-paths.md` — its per-card **H/U paths are the authoritative test list**: every path of the sections a task covers becomes at least one test (exemplar tests in this plan show the style, not the full list). Its "Locked interpretations" and S1–S15 decisions are binding.
- Also read `docs/EFFECT_AUTHOR_REFERENCE.md` and one existing family-style effect file (`src/goa2/scripts/tigerclaw_effects.py` for defense cards, `src/goa2/scripts/silverarrow_effects.py` for max-range/repeat attacks) before writing effect code.
- Commit directly on `main`. No `Co-Authored-By` lines, no AI-tool mentions in commits.
- New steps MUST add a unique `StepType` in `domain/models/enums.py` and set it as the class `type` default (import-time guard raises otherwise). Same for filters/`FilterType`. New enums/steps that appear in views or events are client contract — update `docs/CLIENT_INTEGRATION_GUIDE.md` when told to.
- Steps that change observable state MUST emit `GameEvent`s; player input MUST use `create_input_request()` — never raw dicts.
- Range/radius/adjacency checks use **topology distance** (pathfinding), never raw hex distance — existing `RangeFilter` already does this; don't hand-roll distance.
- Effect tests: `tests/engine/effects/cases/test_snorri_effects.py`, using `EffectScenarioBuilder` (`tests/engine/effects/builders.py`) + `run_card` (`runner.py`), marked `@pytest.mark.effect_flow` / `@pytest.mark.effect_contract`. Assert behavior, not wiring. Test file basenames unique across `tests/`.
- Ult-dependent paths (marked "(ult)" in the TDD doc) are implemented in **Task 11**, not in the family tasks.
- After EVERY task: `PYTHONPATH=src uv run pytest tests/ -q` passes (760+ existing tests), plus `uv run ruff check src/ && uv run black --check src/ && uv run mypy src/` (pre-commit runs these anyway).

## File Structure

| File | Responsibility |
|---|---|
| `src/goa2/domain/models/enums.py` | `RuneType` enum; new `StepType` values; `PassiveTrigger.BEFORE_DEFENSE` |
| `src/goa2/domain/models/unit.py` | `Hero.rune_slots` field |
| `src/goa2/domain/events.py` | `GameEventType.RUNES_PLACED` |
| `src/goa2/domain/views.py` | `rune_slots` in the hero view dict (public) |
| `src/goa2/engine/steps/markers.py` | `PlaceRunesStep` (sequential placement prompts) |
| `src/goa2/engine/steps/selection.py` | `ChooseRuneStep` (generic rune option prompt) |
| `src/goa2/engine/steps/combat.py` | `attack_is_basic` context flag; `SnapshotAdjacentHeroesStep` |
| `src/goa2/engine/steps/cards.py` | `SwapItemCardStep` |
| `src/goa2/engine/steps/reactions.py` | fire `BEFORE_DEFENSE` passives; `_PER_DEFENSE_KEYS` addition |
| `src/goa2/engine/steps/__init__.py` | re-export new steps |
| `src/goa2/scripts/snorri_effects.py` | `active_runes()` helper + all 9 effect classes |
| `tests/engine/effects/cases/test_snorri_effects.py` | all TDD-doc paths |
| `tests/engine/test_rune_slots.py` | P1 model/view/persistence tests |
| `docs/CLIENT_INTEGRATION_GUIDE.md` | view addition (`rune_slots`), new event type |

---

### Task 1: `RuneType` + `Hero.rune_slots` + view exposure + event (P1)

**Files:**
- Modify: `src/goa2/domain/models/enums.py` (add `RuneType`)
- Modify: `src/goa2/domain/models/unit.py` (Hero field)
- Modify: `src/goa2/domain/models/__init__.py` (export `RuneType`)
- Modify: `src/goa2/domain/events.py` (`GameEventType.RUNES_PLACED = "runes_placed"`)
- Modify: `src/goa2/domain/views.py` (hero dict — next to `"items"`)
- Modify: `docs/CLIENT_INTEGRATION_GUIDE.md` (hero view structure + event type)
- Test: `tests/engine/test_rune_slots.py`

**Interfaces:**
- Produces: `RuneType(StrEnum)` with `AXE="axe"`, `BIRD="bird"`, `ANVIL="anvil"`, `HORN="horn"`; `Hero.rune_slots: dict[int, RuneType]` (default `{}`, keys 1–4); hero view gains `"rune_slots": {"1": "axe", ...}` (string keys, visible to ALL viewers incl. opponents/spectators); `GameEventType.RUNES_PLACED`.

- [ ] **Step 1: Write the failing tests** (`tests/engine/test_rune_slots.py`)

```python
"""P1: rune_slots field, persistence invariants, view exposure."""

from goa2.domain.models import Hero, RuneType, TeamColor
from goa2.domain.state import GameState
from goa2.domain.views import build_view

from tests.engine.effects.builders import EffectScenarioBuilder

RUNES = {1: RuneType.AXE, 2: RuneType.BIRD, 3: RuneType.ANVIL, 4: RuneType.HORN}


def _state() -> GameState:
    return (
        EffectScenarioBuilder()
        .line_board()
        .red_hero("hero_snorri", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(3, 0, -3))
        .with_actor("hero_snorri")
        .build()
    )


def test_rune_slots_default_empty():
    assert Hero(id="hero_x", name="X", deck=[]).rune_slots == {}


def test_rune_slots_survive_retrieve_cards():
    state = _state()
    snorri = state.get_hero("hero_snorri")
    snorri.rune_slots = dict(RUNES)
    snorri.retrieve_cards()  # end-of-round card cleanup
    assert snorri.rune_slots == RUNES


def test_rune_slots_serialization_roundtrip():
    state = _state()
    state.get_hero("hero_snorri").rune_slots = dict(RUNES)
    restored = GameState.model_validate_json(state.model_dump_json())
    assert restored.get_hero("hero_snorri").rune_slots == RUNES


def test_rune_slots_public_in_opponent_view():
    state = _state()
    state.get_hero("hero_snorri").rune_slots = dict(RUNES)
    view = build_view(state, for_hero_id="hero_knight")
    snorri_view = _find_hero(view, "hero_snorri")
    assert snorri_view["rune_slots"] == {"1": "axe", "2": "bird", "3": "anvil", "4": "horn"}


def _find_hero(view: dict, hero_id: str) -> dict:
    for team in view["teams"].values():
        for hero in team["heroes"]:
            if hero["id"] == hero_id:
                return hero
    raise AssertionError(f"{hero_id} not in view")
```

(Adjust `_find_hero` to the actual `build_view()` shape — read `domain/views.py` first; the assertion on content stays.)

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=src uv run pytest tests/engine/test_rune_slots.py -q` → ImportError (`RuneType`).
- [ ] **Step 3: Implement** — `RuneType` in enums.py; on `Hero`: `rune_slots: dict[int, RuneType] = Field(default_factory=dict)`; in views.py hero-dict builder add `"rune_slots": {str(k): v.value for k, v in hero.rune_slots.items()}`; add `RUNES_PLACED` to `GameEventType`.
- [ ] **Step 4: Run** — tests pass; full suite passes.
- [ ] **Step 5: Update `docs/CLIENT_INTEGRATION_GUIDE.md`** — hero view field + `runes_placed` event.
- [ ] **Step 6: Commit** — `feat: rune_slots hero field, view exposure, RUNES_PLACED event`

---

### Task 2: `PlaceRunesStep`, `active_runes()`, Inscribe the Runes (P2, TDD §1)

**Files:**
- Modify: `src/goa2/domain/models/enums.py` (`StepType.PLACE_RUNES = "place_runes"`)
- Modify: `src/goa2/engine/steps/markers.py` (new step), `src/goa2/engine/steps/__init__.py` (export)
- Create: `src/goa2/scripts/snorri_effects.py`
- Test: `tests/engine/effects/cases/test_snorri_effects.py` (new file, §1 paths H1–H6, U1)

**Interfaces:**
- Produces:
  - `PlaceRunesStep(GameStep)` with `hero_id: str`; prompts `SELECT_OPTION` per slot 1→3 offering the not-yet-placed runes (option `id` = rune value), **auto-places the 4th**, then overwrites `hero.rune_slots` and emits `GameEvent(RUNES_PLACED)` with the arrangement in its payload.
  - `active_runes(state: GameState, card: Card, context: dict) -> set[RuneType]` in `snorri_effects.py`: finds the rune owner (the hero owning `card` — scan `state` heroes' containers incl. `ultimate_card`; NOT the current actor, so Mind-Gripped copies still see runes, TDD §19) and returns `{owner.rune_slots[state.turn]}` if set, unioned with runes named by context keys `snorri_ult_rune_action` / `snorri_ult_rune_defense` (set only in Task 11).
  - `@register_effect("inscribe_the_runes") class InscribeTheRunesEffect(CardEffect)` — `build_steps` returns `[PlaceRunesStep(hero_id=hero.id)]`.

- [ ] **Step 1: Write failing tests** — §1 H1–H6 + U1 from the TDD doc. Exemplar (H1 + H6):

```python
import pytest

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import RuneType
from tests.engine.effects.builders import EffectScenarioBuilder
from tests.engine.effects.runner import run_card


def snorri_card(card_id: str):
    """Fetch a real Snorri card (fresh copy) from the registry."""
    hero = HeroRegistry.create("hero_snorri")  # match existing registry API
    for c in hero.deck + ([hero.ultimate_card] if hero.ultimate_card else []):
        if c.id == card_id:
            return c.model_copy(deep=True)
    raise LookupError(card_id)


def snorri_state(card_id: str, *, turn: int = 1, runes: dict[int, RuneType] | None = None):
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_snorri", at=(0, 0, 0), current_card=snorri_card(card_id))
        .blue_hero("hero_knight", at=(1, 0, -1))
        .with_actor("hero_snorri")
        .build()
    )
    state.turn = turn
    if runes:
        state.get_hero("hero_snorri").rune_slots = dict(runes)
    return state


@pytest.mark.effect_flow
def test_inscribe_places_four_runes_with_choice():  # §1 H1
    state = snorri_state("inscribe_the_runes")
    run = run_card(state, "hero_snorri")
    run.expect_input("SELECT_OPTION").choose("axe")
    run.expect_input("SELECT_OPTION").choose("bird")
    run.expect_input("SELECT_OPTION").choose("anvil")  # horn auto-placed
    run.finish()
    assert state.get_hero("hero_snorri").rune_slots == {
        1: RuneType.AXE, 2: RuneType.BIRD, 3: RuneType.ANVIL, 4: RuneType.HORN,
    }
    assert "runes_placed" in [e.event_type.value for e in run.events]
```

(Check the actual `HeroRegistry` accessor name in `src/goa2/data/heroes/registry.py` before using it.)

- [ ] **Step 2: Verify failure** (effect not registered → card resolves without prompts).
- [ ] **Step 3: Implement** `PlaceRunesStep` (model on `GuessCardColorStep` at `engine/steps/selection.py:740` for the prompt/pending_input pattern; keep placement progress in step fields so it survives re-entry), `active_runes()`, `InscribeTheRunesEffect`.
- [ ] **Step 4: Run §1 tests + full suite.**
- [ ] **Step 5: Commit** — `feat: Snorri Inscribe the Runes + active_runes helper`

---

### Task 3: `attack_is_basic` context flag (P4)

**Files:**
- Modify: `src/goa2/engine/steps/combat.py` (`AttackSequenceStep.resolve`, next to the `attack_is_ranged` write at ~line 104)
- Test: `tests/engine/test_rune_slots.py` (append) or a focused test in `tests/engine/`

**Interfaces:**
- Produces: `context["attack_is_basic"]: bool` — True iff the attack's source card color is GOLD or SILVER. Source card = the acting hero's `current_turn_card` unless the context already carries a performing-card override (follow how `attack_is_ranged` finds its card; set both flags at the same site, every resolve, so it can't leak between attacks).

- [ ] **Step 1: Failing test** — build a state where the attacker's `current_turn_card` is a SILVER card (use `builders.movement_card`-style factory with `CardColor.SILVER` and `ActionType.ATTACK`), push `AttackSequenceStep`, assert `context["attack_is_basic"] is True`; second test with a RED card → False.
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: attack_is_basic context flag for basic-attack defenses`

---

### Task 4: Oath family — Endurance / Fortitude / Perseverance (TDD §9–§11, S8)

**Files:**
- Modify: `src/goa2/scripts/snorri_effects.py`
- Test: `tests/engine/effects/cases/test_snorri_effects.py` (§9 H1–H2/U1–U4, §10, §11 H1–H2/U1; §11 H3 deferred to Task 11)

**Interfaces:**
- Produces: one `OathEffect` base registered for `oath_of_endurance`, `oath_of_fortitude`, `oath_of_perseverance`, parametrized by `rune_blocks: dict[RuneType, str]` (endurance: horn→"basic", axe→"melee"; fortitude adds bird→"ranged"; perseverance all four incl. anvil→"non_basic") and `choose_one: bool` (perseverance only).
- Consumes: `attack_is_basic` / `attack_is_ranged` context flags (Task 3), `active_runes()` (Task 2).

Block predicate per type: `basic → context["attack_is_basic"]`; `melee → not context["attack_is_ranged"]`; `ranged → context["attack_is_ranged"]`; `non_basic → not context["attack_is_basic"]`.

- [ ] **Step 1: Failing tests.** Model the defense flow on `tests/engine/effects/cases/test_dodger_effects.py` / tigerclaw block tests (read one first). Exemplar (§9 H1):

```python
@pytest.mark.effect_flow
def test_oath_endurance_blocks_basic_attack_and_grants_immunity():  # §9 H1
    # Enemy knight attacks with a SILVER (basic) card; Snorri defends with
    # Oath of Endurance; horn rune active this turn.
    state = attack_scenario(  # helper assembled per tigerclaw test pattern
        attacker="hero_knight", attack_card_color=CardColor.SILVER,
        defender="hero_snorri", defense_card=snorri_card("oath_of_endurance"),
        defender_runes={1: RuneType.HORN, 2: RuneType.AXE, 3: RuneType.BIRD, 4: RuneType.ANVIL},
        turn=1,
    )
    run = run_attack_with_defense(state)  # drives ReactionWindow → choose Oath
    run.finish()
    snorri = state.get_hero("hero_snorri")
    assert snorri.current_health_unchanged  # blocked — assert via damage events == []
    assert any(
        e.effect_type == EffectType.IMMUNITY_ENEMY_ACTIONS and e.is_active
        for e in state.active_effects
    )
```

(The two helpers are file-local, built once, reused by all Oath tests; write them from the existing defense-test pattern — do NOT invent new framework.)

- [ ] **Step 2: Verify failure.**
- [ ] **Step 3: Implement** — `build_defense_steps`: compute `active = active_runes(...)`; map to block types; `choose_one` with >1 active → `ChooseRuneStep` limited to active runes (auto when 1 — no prompt); matched → `SetContextFlagStep(key="auto_block", value=True)`, else `defense_invalid` (Dodger `dodge` pattern, `tigerclaw_effects.py:60`). `build_on_block_steps`: `CreateEffectStep` for `IMMUNITY_ENEMY_ACTIONS`, `THIS_TURN`, affects SELF — on-block steps already run after `ResolveCombatStep` (S8 satisfied; verify ordering in `AttackSequenceStep` expansion). NOTE: `ChooseRuneStep` is introduced here (new `StepType.CHOOSE_RUNE`, `engine/steps/selection.py`, modeled on `GuessCardColorStep`): fields `output_key: str`, `options: list[str]`, `prompt: str`; stores chosen rune value in context.
- [ ] **Step 4: Run §9–11 tests + full suite.**
- [ ] **Step 5: Commit** — `feat: Snorri Oath defense family with rune-gated blocks`

---

### Task 5: Dagger / Hammer / Battleaxe family (TDD §2–§4)

**Files:**
- Modify: `src/goa2/scripts/snorri_effects.py`
- Test: `test_snorri_effects.py` (§2 all, §3 all, §4 H3/H4/U3/U4; §4 H5/H6 deferred to Task 11)

**Interfaces:**
- Produces: `RunicMeleeEffect` base registered for `runic_dagger`, `runic_hammer`, `runic_battleaxe`; parametrized `has_pre_move: bool`, `has_repeat: bool`.
- Consumes: `active_runes()`.

Sequence builder (single source for base + repeat, per interp 6 full-sequence repeat):

```python
def _sequence(self, state, hero, stats, active, *, repeat_leg: bool) -> list[GameStep]:
    steps: list[GameStep] = []
    if self.has_pre_move and RuneType.HORN in active:
        steps += optional_move(hero, spaces=1)  # SelectStep(HEX, optional) + MoveUnitStep
    target_filters = (
        [UnitTypeFilter(unit_type="MINION"), TeamFilter(relation="ENEMY")] if repeat_leg else []
    )
    steps.append(AttackSequenceStep(damage=stats.primary_value, range_val=1,
                                    target_filters=target_filters))
    if RuneType.ANVIL in active:
        steps.append(RetrieveCardStep(...optional, own discard...))  # match RetrieveCardStep API
    return steps
```

The repeat is offered once after the base sequence (axe active, `has_repeat`): a `CONFIRM_PASSIVE`-style optional gate, then push `_sequence(repeat_leg=True)`. Read how an existing repeat is gated (`silverarrow_effects.py`) and reuse that step/pattern rather than inventing one.

- [ ] **Step 1: Failing tests** — every §2/§3 path + §4 non-ult paths (each H/U from the TDD doc = 1 test; name tests `test_<card>_<path>` e.g. `test_runic_hammer_h1_horn_premove_then_adjacent_attack`).
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Snorri runic melee family (dagger/hammer/battleaxe)`

---

### Task 6: Runecaster / Runeblaster + adjacency snapshot (TDD §5–§6, P5, S2, S13)

**Files:**
- Modify: `src/goa2/domain/models/enums.py` (`StepType.SNAPSHOT_ADJACENT_HEROES`)
- Modify: `src/goa2/engine/steps/combat.py` (new step), `engine/steps/__init__.py`
- Modify: `src/goa2/scripts/snorri_effects.py`
- Test: `test_snorri_effects.py` (§5 all, §6 H1/U1; §6 H2 deferred to Task 11)

**Interfaces:**
- Produces:
  - `SnapshotAdjacentHeroesStep(GameStep)`: fields `target_key: str = "target_id"`, `output_key: str`, `relation: str = "ENEMY"`; stores in `context[output_key]` the list of enemy-hero unit ids adjacent (topology) to the unit at `context[target_key]` at resolve time. No input, no events.
  - `RunicRangedEffect` registered for `runecaster` (exact max range) / `runeblaster` (bird → whole range).
- Consumes: `active_runes()`, `ForceDiscardOrDefeatStep` (existing, `engine/steps/cards.py:457`), `ExcludeIdentityFilter`.

Assembly: select target FIRST with an explicit `SelectStep(UNIT, output_key="target_id", filters=[TeamFilter(ENEMY), RangeFilter(min_range=r, max_range=r), ImmunityFilter(...)])` (drop `min_range` when bird active — S13), then `SnapshotAdjacentHeroesStep(output_key="rc_adjacent")` (targeting-time snapshot, interp 5), then `AttackSequenceStep(damage=..., range_val=r, is_ranged=True, target_id_key="target_id")`, then riders: horn → optional move up to 2 (`MoveSequenceStep`-free nudge: SelectStep + MoveUnitStep per feedback memory); axe → `SelectStep` over ids in `rc_adjacent` (use the existing context-id-list selection mechanism — check `SelectStep`/filters for an ids-from-context option; if none exists add `ContextIdsFilter` with a new `FilterType`) + `ForceDiscardOrDefeatStep`.

- [ ] **Step 1: Failing tests** — include §5 H6 (push the target away between targeting and rider via a scripted defense… simplest: assert snapshot content in context after the attack with the target defeated — behavior-level: the discard prompt still lists the hero who WAS adjacent).
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Snorri runecaster/runeblaster with targeting-time adjacency rider`

---

### Task 7: Runetrap / Runebomb (TDD §7–§8, S7)

**Files:**
- Modify: `src/goa2/scripts/snorri_effects.py`
- Test: `test_snorri_effects.py` (§7 all, §8 H1/H2/U1; §8 H3 deferred to Task 11)

**Interfaces:**
- Produces: `RuneDiscardEffect` registered for `runetrap` (horn→GREEN, axe→SILVER, anvil→BLUE; no bird) and `runebomb` (`choose_one=True`, + bird→GOLD).
- Consumes: `ForceDiscardByColorStep` (`engine/steps/cards.py:401` — takes `victim_key`, `color`; victim picks the card; silently fizzles when no match), `ChooseRuneStep` (Task 4), `active_runes()`.

Flow: compute active runes → `runebomb`: one rune (auto if single, `ChooseRuneStep` if two — Task 11 territory but wire it now, gated on len>1) → bullets = active∩mapping (one bullet for runebomb) → if any bullet: ONE `SelectStep(UNIT, output_key="rt_victim", filters=[TeamFilter(ENEMY), UnitTypeFilter(HERO), RangeFilter(max_range=stats.radius), ImmunityFilter()])` (interp 11: one hero for all bullets) → one `ForceDiscardByColorStep(victim_key="rt_victim", color=...)` per bullet in printed order.

- [ ] **Step 1: Failing tests** (all §7/§8 non-ult paths; parametrize the three §7 color cases).
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Snorri runetrap/runebomb color discards`

---

### Task 8: Passage family (TDD §12–§14, S6)

**Files:**
- Modify: `src/goa2/scripts/snorri_effects.py`
- Test: `test_snorri_effects.py` (§12 all, §13 all, §14 H1/U1; §14 H2/H3 deferred to Task 11)

**Interfaces:**
- Produces: `PassageEffect` registered for `safe_passage` (bird), `hidden_passage` (+anvil), `deep_passage` (+horn).
- Consumes: `MoveSequenceStep(range_val=..., pass_through_obstacles=...)` (Bain precedent, `bain_effects.py:209`) — this IS the primary movement action so `MoveSequenceStep` is correct (feedback memory: movement-action entry point); `CreateEffectStep` + `IMMUNITY_ENEMY_ACTIONS` (Whisper `death_seeker`, `whisper_effects.py:1139` for the exact CreateEffectStep parameters).

`build_steps`: `movement = stats.primary_value + (2 if horn active and deep else 0)`; if bird active → offer the ignore as a choice? **No** — simplest faithful S6: `pass_through_obstacles=True` grants the OPTION at pathfinding level (a legal normal path remains choosable), so a single `MoveSequenceStep(range_val=movement, pass_through_obstacles=bird_active)`. Anvil active → append immunity `CreateEffectStep` after the move.

- [ ] **Step 1: Failing tests** — §12 H1 must assert a path THROUGH an obstacle hex to a free hex beyond it succeeds; §12 U1 the same destination is rejected.
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Snorri passage family`

---

### Task 9: `SwapItemCardStep` + Ancestral Boon / Grace (TDD §15–§16, P7, S10, S11)

**Files:**
- Modify: `src/goa2/domain/models/enums.py` (`StepType.SWAP_ITEM_CARD`)
- Modify: `src/goa2/engine/steps/cards.py` (new step next to `ConvertCardToItemStep:1867` — read it first: it defines where ITEM-state cards live and how `hero.items` is incremented)
- Modify: `src/goa2/scripts/snorri_effects.py`
- Test: `test_snorri_effects.py` (§15 all, §16 H1–H3/U1/U2; §16 H4 deferred to Task 11)

**Interfaces:**
- Produces:
  - `SwapItemCardStep(GameStep)`: fields `hero_key: str`, `item_card_key: str`, `target_card_key: str`. Semantics (interp 10): item card X (state ITEM) and card Y (same hero, same tier+color, any non-ITEM location). After: Y has `state=ITEM` (+1 `hero.items[Y.item]`), X occupies Y's former location/state (−1 `hero.items[X.item]`). Emits a `GameEvent` (existing generic card/state event type — match what `ConvertCardToItemStep` emits). Follow `Hero.swap_cards` for the location bookkeeping but handle the ITEM state manually (swap_cards doesn't know ITEM).
  - `AncestralEffect` registered for `ancestral_boon` (axe, anvil) / `ancestral_grace` (+bird).
- Consumes: `SwapCardStep`/`Hero.swap_cards` (axe bullet: resolved↔hand), `RetrieveCardStep` or direct retrieve-all steps (anvil bullet — check `RetrieveCardStep` for an all-mode; else loop `RetrieveCardStep` or a small dedicated step), `ExcludeIdentityFilter(exclude_self=True)` + `ImmunityFilter` on hero selection (S10), `override_player_id_key`-style routing so the AFFECTED player answers card choices (interp 12 — `ForceDiscardByColorStep:401` shows the routing pattern).

Flow: Snorri: `SelectStep(UNIT, output_key="ab_hero", filters=[TeamFilter(FRIENDLY), UnitTypeFilter(HERO), RangeFilter(max_range=stats.radius), ExcludeIdentityFilter(exclude_self=True), ImmunityFilter()], is_mandatory=False)` → per active bullet in printed order, steps routed to the chosen hero's player, each optional; bird bullet gated on S11 eligibility (≥1 ITEM card with a same-tier+color non-ITEM card).

- [ ] **Step 1: Failing tests** — for §16 H1: level a helper hero so they own an ITEM-state card (call `ConvertCardToItemStep` machinery or set card state + items dict directly in the builder), then assert both the items dict delta and X landing in Y's slot.
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Snorri ancestral family + item card swap step`

---

### Task 10: Rune Sigils (TDD §17, S9, S12)

**Files:**
- Modify: `src/goa2/scripts/snorri_effects.py`
- Test: `test_snorri_effects.py` (§17 H1–H5/H8/U1–U3; H6/H7 deferred to Task 11)

**Interfaces:**
- Produces: `RuneSigilsEffect` registered for `rune_sigils`.
- Consumes: `GainCoinsStep` (`engine/steps/cards.py:1320`), `active_runes()`, repeat gate pattern from Task 5.

Assembly: damage = `stats.primary_value + (3 if axe active else 0)` (or `damage_bonus_key`); targeting: adjacent unit (`RangeFilter(max_range=1)`), bird active → alternative select over enemy minions `RangeFilter(max_range=stats.range)` (S12) offered as a choice before targeting; anvil → after each attack instance, if that instance's target is a hero → `GainCoinsStep(amount=3)` (gate on target unit type via a small check step or conditional assembly per instance); horn → optional repeat on a different enemy hero within `stats.range` (`ExcludeIdentityFilter(exclude_keys=["target_id"])`... use the first instance's target id from a saved context key). `is_ranged=True` on all instances (H1 contract: adjacent attack from this card is still RANGED — assert an Oath-of-Fortitude-style ranged block can block it, or assert `attack_is_ranged` contract per existing convention in `test_combat_flag_scoping.py`).

- [ ] **Step 1: Failing tests** (§17 non-ult paths).
- [ ] **Step 2–4: Fail → implement → pass** (full suite).
- [ ] **Step 5: Commit** — `feat: Snorri rune sigils`

---

### Task 11: Rune Mastery ultimate + BEFORE_DEFENSE trigger + all deferred (ult) paths (TDD §18, §19, P3, S4, S5, S14)

**Files:**
- Modify: `src/goa2/domain/models/enums.py` (`PassiveTrigger.BEFORE_DEFENSE = "before_defense"`)
- Modify: `src/goa2/engine/steps/reactions.py` (fire the trigger; extend `_PER_DEFENSE_KEYS`)
- Modify: `src/goa2/scripts/snorri_effects.py`
- Test: `test_snorri_effects.py` (§18 all, §19 both, §4 H5/H6, §6 H2, §8 H3, §11 H3, §14 H2/H3, §16 H4, §17 H6/H7)

**Interfaces:**
- Produces:
  - `RuneMasteryEffect` registered for `rune_mastery`: `get_passive_config()` → `PassiveConfig(trigger=PassiveTrigger.BEFORE_ACTION, is_optional=False, uses_per_turn=-1)`; `should_offer_passive` → False when `hero.rune_slots` is empty (S5/interp 3); `get_passive_steps` → `ChooseRuneStep(output_key="snorri_ult_rune_action", options=<the 3 inactive placed runes>, prompt="Rune Mastery: choose a second active rune")`. Add a second config path for `PassiveTrigger.BEFORE_DEFENSE` writing `snorri_ult_rune_defense` (check whether `get_passive_config` supports multiple triggers; if it's single-trigger, extend the effect API the way `CheckPassiveAbilitiesStep:496` consumes it — smallest change wins).
  - In `ReactionWindowStep` (or the step that runs right after the defense card is chosen and before `ResolveDefenseTextStep` — read the expansion in `AttackSequenceStep`): push `CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_DEFENSE.value, hero_id=<defender owner id>)`. Add `"snorri_ult_rune_defense"` to `_PER_DEFENSE_KEYS` (`reactions.py:24`). Do NOT add the action key there.
  - `BEFORE_ACTION` already fires for primary/secondary/HOLD (`engine/steps/cards.py:779`) — the own-action side needs no engine change.
- Consumes: everything from Tasks 2–10.

- [ ] **Step 1: Failing tests** — §18 H1–H5/U1–U2 (level Snorri to 8 in the builder: `hero.level = 8`), §19 H1/U1 (drive NebKher's Mind Grip on a Snorri prev-slot card — copy the setup from `test_nebkher_effects.py` Mind Grip tests), plus every deferred "(ult)" path from Tasks 4–10 sections.
- [ ] **Step 2: Verify failures.**
- [ ] **Step 3: Implement** (ultimate effect, BEFORE_DEFENSE firing, per-defense key clearing).
- [ ] **Step 4: Run the full Snorri file + entire suite.**
- [ ] **Step 5: Commit** — `feat: Snorri Rune Mastery ultimate incl. defense-reaction trigger`

---

### Task 12: Final sweep — quality gates, docs, spec status

**Files:**
- Modify: `docs/superpowers/plans/2026-07-10-snorri-tdd-paths.md` (status header → IMPLEMENTED)
- Modify: `docs/CLIENT_INTEGRATION_GUIDE.md` (verify Task 1 additions landed; add any new InputRequest usages if shapes changed — they should not have)

- [ ] **Step 1:** `PYTHONPATH=src uv run pytest tests/ -q` — everything green.
- [ ] **Step 2:** `uv run ruff check src/ && uv run black src/ && uv run mypy src/` — clean.
- [ ] **Step 3:** Cross-check every H/U path in the TDD doc has a matching test (grep test names per section); add any missed.
- [ ] **Step 4:** Update the TDD doc status header; verify client guide.
- [ ] **Step 5: Commit** — `docs: mark Snorri implemented; client guide updates`

---

## Self-Review Notes

- **Spec coverage:** §1→T2, §2–4→T5, §5–6→T6, §7–8→T7, §9–11→T4, §12–14→T8, §15–16→T9, §17→T10, §18–19→T11; P1→T1, P2→T2, P3→T11, P4→T3, P5→T6, P6→T4 (on-block ordering), P7→T9. All covered.
- **Type consistency:** `active_runes(state, card, context)` defined T2, consumed T4–T11; `ChooseRuneStep(output_key, options, prompt)` defined T4, consumed T7/T11; context keys `snorri_ult_rune_action`/`snorri_ult_rune_defense` fixed here and in the TDD doc's P2.
- **Known judgment calls for implementers:** exact `RetrieveCardStep`/retrieve-all API (T5/T9), `HeroRegistry` accessor (T2), ids-from-context filter existence (T6), multi-trigger passive config (T11) — each task says to read the named file first and adapt the smallest way.
