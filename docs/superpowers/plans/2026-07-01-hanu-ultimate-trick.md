# Hanu — The Ultimate Trick Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Hanu's purple ultimate: when level-8 Hanu resolves Hurry Up! on a hero, Hanu's player answers every input during that hero's next action (that card, this round) — actor and legality stay with the controlled hero.

**Architecture:** A `CONTROL_NEXT_ACTION` `ActiveEffect` (created by a new `ScheduleActionControlStep` appended to Hurry Up!) records controller, target, and the targeted card id. A single remap at the handler's input-return choke point rewrites `InputRequest.player_id` from the controlled hero to Hanu while that hero is the current actor resolving that exact card. Spec: `docs/superpowers/specs/2026-07-01-hanu-ultimate-trick-design.md`.

**Tech Stack:** Python 3.11, Pydantic V2, pytest.

## Global Constraints

- Run tests as `PYTHONPATH=src uv run pytest <path> -q` from the repo root.
- Commit directly on `main`. No `Co-Authored-By:` lines; never mention Claude/Claude Code in commits.
- New `StepType` enum value + `GameStep` subclass is the full serialization registration (`AnyStep` union auto-builds from subclasses in `engine/step_types.py`); no manual union edit needed.
- Client-contract files touched (`domain/input.py`) require a `docs/CLIENT_INTEGRATION_GUIDE.md` update (Task 3).
- Fluent effect tests live in `tests/engine/effects/cases/test_hanu_effects.py` and use `EffectScenarioBuilder` + `run_card` (see existing Hurry Up! section, lines ~834-948).

---

### Task 1: Control effect model + `ScheduleActionControlStep` + Hurry Up! wiring

**Files:**
- Modify: `src/goa2/domain/models/effect.py` (EffectType enum ~line 102; ActiveEffect fields ~line 200)
- Modify: `src/goa2/domain/models/enums.py` (StepType, after `RESTORE_CARD_INITIATIVE = "restore_card_initiative"`, line 216)
- Modify: `src/goa2/engine/steps/effects.py` (new step, place directly after `ScheduleJourneyReturnStep`, which ends ~line 250)
- Modify: `src/goa2/engine/steps/__init__.py` (export, next to `ScheduleJourneyReturnStep` at line 50)
- Modify: `src/goa2/scripts/hanu_effects.py` (HurryUpEffect ~line 509; TheUltimateTrickEffect docstring ~line 541)
- Test: `tests/engine/effects/cases/test_hanu_effects.py` (replace the "PURPLE — DEFERRED" comment block at the end, ~line 946)

**Interfaces:**
- Produces: `EffectType.CONTROL_NEXT_ACTION`; `ActiveEffect.controlled_card_id: str | None`; `StepType.SCHEDULE_ACTION_CONTROL`; `ScheduleActionControlStep(hero_key: str)` (reads target hero id from context). Task 2's handler remap matches on `effect_type == EffectType.CONTROL_NEXT_ACTION`, `effect.is_active`, `effect.scope.origin_id == <controlled hero id>`, `effect.controlled_card_id == <card id>`, controller = `effect.source_id`.

- [ ] **Step 1: Write the failing tests**

In `tests/engine/effects/cases/test_hanu_effects.py`, replace the trailing comment block

```python
# =============================================================================
# PURPLE — The Ultimate Trick (DEFERRED): registered but inert.
# =============================================================================
```

with:

```python
# =============================================================================
# PURPLE — The Ultimate Trick: "You choose the next action, and how it is
# performed, for a hero you target with the Hurry Up!."
# Level 8 passive. Hurry Up! records a CONTROL_NEXT_ACTION effect; the handler
# reroutes the controlled hero's inputs to Hanu while they resolve that card.
# Only the decision-maker changes — actor/legality stay the controlled hero.
# =============================================================================


def _ultimate_state(*, enemy_card=None):
    """Level-8 Hanu with ultimate, about to play Hurry Up! on blue_enemy."""
    target_card = enemy_card if enemy_card is not None else hero_card("Hanu", "monkey_trick")
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(5))
        .red_hero("hero_hanu", at=(0, 0, 0), current_card=hero_card("Hanu", "hurry_up"))
        .blue_hero("blue_enemy", at=(2, 0, -2), current_card=target_card)
        .with_unresolved_heroes(["blue_enemy"])
        .with_actor("hero_hanu")
        .build()
    )
    hanu = state.get_hero("hero_hanu")
    hanu.level = 8
    hanu.ultimate_card = hero_card("Hanu", "the_ultimate_trick")
    return state


def _play_hurry_up(run):
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    return run.choose("blue_enemy")


@pytest.mark.effect_flow
def test_ultimate_trick_records_control_effect_at_level_8() -> None:
    from goa2.domain.models.effect import DurationType, EffectType

    state = _ultimate_state()
    run = run_card(state, "hero_hanu")
    _play_hurry_up(run).finish()

    effects = [
        e for e in state.active_effects if e.effect_type == EffectType.CONTROL_NEXT_ACTION
    ]
    assert len(effects) == 1
    effect = effects[0]
    assert effect.source_id == "hero_hanu"
    assert effect.scope.origin_id == "blue_enemy"
    assert effect.controlled_card_id == "monkey_trick"
    assert effect.duration == DurationType.THIS_ROUND
    assert effect.is_active
    assert any(
        e.event_type == GameEventType.EFFECT_CREATED
        and e.metadata.get("effect") == "action_control"
        for e in run.events
    )


@pytest.mark.effect_flow
def test_ultimate_trick_inactive_below_level_8() -> None:
    from goa2.domain.models.effect import EffectType

    state = _ultimate_state()
    state.get_hero("hero_hanu").level = 7
    run = run_card(state, "hero_hanu")
    _play_hurry_up(run).finish()

    assert not [
        e for e in state.active_effects if e.effect_type == EffectType.CONTROL_NEXT_ACTION
    ]
    # Hurry Up!'s own initiative effect still applies without the ultimate.
    assert state.get_hero("blue_enemy").current_turn_card.initiative == 11


@pytest.mark.effect_flow
def test_ultimate_trick_requires_ultimate_card() -> None:
    from goa2.domain.models.effect import EffectType

    state = _ultimate_state()
    state.get_hero("hero_hanu").ultimate_card = None
    run = run_card(state, "hero_hanu")
    _play_hurry_up(run).finish()

    assert not [
        e for e in state.active_effects if e.effect_type == EffectType.CONTROL_NEXT_ACTION
    ]
```

`GameEventType` is already imported at the top of the file; `pytest`, `hero_card`, `run_card`, `_hex_disk`, `InputRequestType` all already exist in this file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/effects/cases/test_hanu_effects.py -q -k ultimate_trick`
Expected: FAIL / errors — `EffectType` has no attribute `CONTROL_NEXT_ACTION`.

- [ ] **Step 3: Implement**

3a. `src/goa2/domain/models/effect.py` — append to `EffectType` (after `DISCARD_SHIELD`, line 102):

```python
    # Action control (Hanu ultimate — The Ultimate Trick). While the hero at
    # scope.origin_id is the current actor resolving the card with id
    # controlled_card_id, the handler reroutes every InputRequest addressed to
    # them to source_id (Hanu). Only the decision-maker changes: actor and all
    # legality (teams, ranges, filters, stats) remain the controlled hero.
    CONTROL_NEXT_ACTION = "control_next_action"
```

3b. Same file — add to `ActiveEffect` after `isolated_hex` (follow the existing effect-specific payload pattern):

```python
    # CONTROL_NEXT_ACTION: id of the unresolved card whose resolution is
    # controlled. Guards the remap so control fizzles if the card changes.
    controlled_card_id: str | None = None
```

3c. `src/goa2/domain/models/enums.py` — after `RESTORE_CARD_INITIATIVE = "restore_card_initiative"` (line 216):

```python
    SCHEDULE_ACTION_CONTROL = "schedule_action_control"
```

3d. `src/goa2/engine/steps/effects.py` — add directly after `ScheduleJourneyReturnStep` (all imports it needs are already at the top of this module):

```python
class ScheduleActionControlStep(GameStep):
    """Hanu's ultimate (The Ultimate Trick): after Hurry Up! targets a hero,
    record a CONTROL_NEXT_ACTION effect so that when that hero acts to resolve
    the targeted card, every input addressed to them is answered by Hanu's
    player instead (player_id remap in the handler). Only the decision-maker
    changes — the actor, and therefore all legality, remains the controlled
    hero. No-ops unless the acting hero's ultimate is unlocked (level >= 8
    with an ultimate card). Control fizzles if the card leaves UNRESOLVED any
    other way (controlled_card_id guard) or the round ends (THIS_ROUND)."""

    type: StepType = StepType.SCHEDULE_ACTION_CONTROL
    hero_key: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        actor_id = str(state.current_actor_id) if state.current_actor_id else None
        actor = state.get_hero(HeroID(actor_id)) if actor_id else None
        if not actor or actor.level < 8 or not actor.ultimate_card:
            return StepResult(is_finished=True)

        target_id = context.get(self.hero_key)
        if not target_id:
            return StepResult(is_finished=True)
        target = state.get_hero(HeroID(str(target_id)))
        if not target or target.current_turn_card is None:
            return StepResult(is_finished=True)
        card = target.current_turn_card
        if card.state != CardState.UNRESOLVED:
            return StepResult(is_finished=True)

        EffectManager.create_effect(
            state=state,
            source_id=actor_id,
            effect_type=EffectType.CONTROL_NEXT_ACTION,
            scope=EffectScope(shape=Shape.POINT, origin_id=str(target_id)),
            duration=DurationType.THIS_ROUND,
            is_active=True,
            controlled_card_id=card.id,
        )

        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.EFFECT_CREATED,
                    actor_id=actor_id,
                    target_id=str(target_id),
                    metadata={
                        "effect": "action_control",
                        "controller_id": actor_id,
                        "card_id": card.id,
                    },
                )
            ],
        )
```

3e. `src/goa2/engine/steps/__init__.py` — add `ScheduleActionControlStep,` to the `from goa2.engine.steps.effects import (...)` block (alphabetical, next to `ScheduleJourneyReturnStep`) and to `__all__` if the module maintains one.

3f. `src/goa2/scripts/hanu_effects.py` — in `HurryUpEffect.build_steps`, import `ScheduleActionControlStep` alongside the other step imports at the top of the file, and append after `SetCardInitiativeStep`:

```python
            SetCardInitiativeStep(hero_key="hurry_target", value=11),
            # The Ultimate Trick (level 8): Hanu's player controls the
            # target's next action (this card, this round).
            ScheduleActionControlStep(hero_key="hurry_target"),
```

Update `TheUltimateTrickEffect` docstring and section comment (behavior lives in Hurry Up!'s scheduling step; this stays a no-step passive):

```python
# =============================================================================
# PURPLE — The Ultimate Trick
# "You choose the next action, and how it is performed, for a hero you target
#  with the Hurry Up!." Passive: the behavior is implemented by
# ScheduleActionControlStep (appended by Hurry Up!, gated on level 8) plus the
# player_id remap in engine/handler.py. This effect itself contributes no steps.
# =============================================================================


@register_effect("the_ultimate_trick")
class TheUltimateTrickEffect(CardEffect):
    """Passive marker — control logic lives in Hurry Up! + the handler remap."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/effects/cases/test_hanu_effects.py tests/engine/test_persistence.py -q`
Expected: PASS (persistence exercises the auto-built `AnyStep`/effect unions).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(hanu): record CONTROL_NEXT_ACTION effect when level-8 Hanu resolves Hurry Up!"
```

---

### Task 2: Handler `player_id` remap

**Files:**
- Modify: `src/goa2/engine/handler.py` (input-return block, lines 66-75; new helper below `process_stack`)
- Test: `tests/engine/effects/cases/test_hanu_effects.py` (append to the ultimate section from Task 1)

**Interfaces:**
- Consumes: `EffectType.CONTROL_NEXT_ACTION`, `ActiveEffect.controlled_card_id`, effect layout from Task 1.
- Produces: remapped `InputRequest.player_id` (controller hero id) + `InputRequest.context["controlled_hero_id"]` (controlled hero id) — Task 3 surfaces the latter in `to_dict()`.

- [ ] **Step 1: Write the failing tests**

Append to the ultimate section of `tests/engine/effects/cases/test_hanu_effects.py`:

```python
def _basic_attack_card() -> "Card":
    from goa2.domain.models import ActionType, Card, CardColor, CardState, CardTier

    card = Card(
        id="test_basic_attack",
        name="Basic Attack",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=2,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        secondary_actions={},
        is_ranged=True,
        range_value=2,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )
    card.state = CardState.UNRESOLVED
    return card


@pytest.mark.effect_flow
def test_controlled_heroes_inputs_reroute_to_hanu() -> None:
    state = _ultimate_state()
    run = run_card(state, "hero_hanu", finalize_turn=True)
    _play_hurry_up(run)
    # FinalizeHeroTurnStep -> FindNextActorStep picks blue_enemy (initiative 11).
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    assert run.latest_request.player_id == "hero_hanu"
    assert run.latest_request.context["controlled_hero_id"] == "blue_enemy"
    # The remap must not disable rollback: Hanu confirms/rolls back this action.
    assert state.execution_context.get("rollback_disabled") is None


@pytest.mark.effect_flow
def test_controlled_hero_legality_is_relative_to_that_hero() -> None:
    # Pedro (Hanu) controls Wuk but cannot make Wuk attack Wuk's allies:
    # options are computed relative to the controlled hero, not the controller.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(5))
        .red_hero("hero_hanu", at=(0, 0, 0), current_card=hero_card("Hanu", "hurry_up"))
        .blue_hero("blue_enemy", at=(2, 0, -2), current_card=_basic_attack_card())
        .blue_minion("blue_ally_minion", at=(3, 0, -3))  # adjacent to blue_enemy
        .red_minion("red_minion", at=(2, 1, -3))  # adjacent to blue_enemy
        .with_unresolved_heroes(["blue_enemy"])
        .with_actor("hero_hanu")
        .build()
    )
    hanu = state.get_hero("hero_hanu")
    hanu.level = 8
    hanu.ultimate_card = hero_card("Hanu", "the_ultimate_trick")

    run = run_card(state, "hero_hanu", finalize_turn=True)
    _play_hurry_up(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    assert run.latest_request.player_id == "hero_hanu"
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    assert run.latest_request.player_id == "hero_hanu"
    options = _option_set(run)
    assert "red_minion" in options  # blue_enemy's enemies are attackable
    assert "blue_ally_minion" not in options  # blue_enemy's own ally is not


@pytest.mark.effect_flow
def test_defender_inputs_during_controlled_turn_stay_with_defender() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(5))
        .red_hero("hero_hanu", at=(0, 0, 0), current_card=hero_card("Hanu", "hurry_up"))
        .red_hero("red_ally", at=(2, 1, -3))  # adjacent to blue_enemy
        .blue_hero("blue_enemy", at=(2, 0, -2), current_card=_basic_attack_card())
        .with_unresolved_heroes(["blue_enemy"])
        .with_actor("hero_hanu")
        .build()
    )
    hanu = state.get_hero("hero_hanu")
    hanu.level = 8
    hanu.ultimate_card = hero_card("Hanu", "the_ultimate_trick")

    run = run_card(state, "hero_hanu", finalize_turn=True)
    _play_hurry_up(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("red_ally").expect_input("SELECT_CARD_OR_PASS")
    assert run.latest_request.player_id == "red_ally"
    assert "controlled_hero_id" not in run.latest_request.context


@pytest.mark.effect_flow
def test_control_fizzles_if_targeted_card_changes() -> None:
    from goa2.domain.types import HeroID

    state = _ultimate_state()
    run = run_card(state, "hero_hanu")
    _play_hurry_up(run).finish()

    # The targeted card leaves UNRESOLVED some other way (replaced here);
    # control must not latch onto the replacement.
    state.get_hero("blue_enemy").current_turn_card = hero_card("Hanu", "this_way")
    state.current_actor_id = HeroID("blue_enemy")
    run2 = run_card(state, "blue_enemy")
    run2.expect_input(InputRequestType.CHOOSE_ACTION)
    assert run2.latest_request.player_id == "blue_enemy"
    assert "controlled_hero_id" not in run2.latest_request.context


@pytest.mark.effect_flow
def test_control_expires_at_end_of_round() -> None:
    from goa2.domain.models.effect import DurationType, EffectType
    from goa2.engine.effect_manager import EffectManager

    state = _ultimate_state()
    run = run_card(state, "hero_hanu")
    _play_hurry_up(run).finish()

    EffectManager.expire_effects(state, DurationType.THIS_ROUND)
    assert not [
        e for e in state.active_effects if e.effect_type == EffectType.CONTROL_NEXT_ACTION
    ]
```

Note for the implementer: `run_card(state, hero_id)` does not set `state.current_actor_id`; the natural-flow tests get it set by `FindNextActorStep` (via `finalize_turn=True`), the fizzle test sets it manually.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/effects/cases/test_hanu_effects.py -q -k "controlled or fizzles or expires"`
Expected: the reroute/legality/fizzle tests FAIL on `player_id == "hero_hanu"` assertions (requests still carry `blue_enemy`); the expiry test may already pass (Task 1 set THIS_ROUND).

- [ ] **Step 3: Implement the remap**

In `src/goa2/engine/handler.py`:

3a. Add a helper after `push_steps` (imports: `EffectType` from `goa2.domain.models.effect` at the top of the file):

```python
def _action_controller(state: GameState, player_id: str) -> str | None:
    """The Ultimate Trick (Hanu): if `player_id` is the current actor and an
    active CONTROL_NEXT_ACTION effect targets them for the exact card they are
    resolving, return the controller's hero id. The remap changes only who
    answers — options/legality were already computed relative to the actor."""
    if state.current_actor_id is None or player_id != str(state.current_actor_id):
        return None
    hero = state.get_hero(state.current_actor_id)
    if hero is None or hero.current_turn_card is None:
        return None
    for effect in state.active_effects:
        if (
            effect.effect_type == EffectType.CONTROL_NEXT_ACTION
            and effect.is_active
            and effect.scope.origin_id == player_id
            and effect.controlled_card_id == hero.current_turn_card.id
        ):
            return effect.source_id
    return None
```

3b. Replace the `requires_input` block (lines 66-75) with:

```python
        if result.requires_input:
            state.execution_stack.append(current_step)
            request = result.input_request
            controller_id = _action_controller(state, request.player_id) if request else None
            if request is not None and controller_id is not None:
                request.context["controlled_hero_id"] = request.player_id
                request.player_id = controller_id
            # Track rollback disabled: if input targets someone other than the
            # current actor. A control remap does NOT disable rollback — the
            # controller confirms/rolls back the controlled action.
            if (
                request is not None
                and controller_id is None
                and state.current_actor_id is not None
                and request.player_id != str(state.current_actor_id)
            ):
                state.execution_context["rollback_disabled"] = True
            return StackResult(input_request=request, events=collected_events)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/effects/cases/test_hanu_effects.py -q`
Expected: PASS. Then run the engine suite to catch regressions in the touched hot loop:
`PYTHONPATH=src uv run pytest tests/engine/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(hanu): reroute controlled hero's inputs to Hanu via handler player_id remap"
```

---

### Task 3: Client contract surfacing + docs + full suite

**Files:**
- Modify: `src/goa2/domain/input.py` (`to_dict()`, after the base `result` dict ~line 176)
- Modify: `docs/CLIENT_INTEGRATION_GUIDE.md` (new subsection near the input-request documentation)
- Test: `tests/engine/effects/cases/test_hanu_effects.py` (one assertion appended)

**Interfaces:**
- Consumes: `InputRequest.context["controlled_hero_id"]` set by Task 2.
- Produces: `to_dict()["controlled_hero_id"]` (only present during controlled actions) — the client-facing signal.

- [ ] **Step 1: Write the failing test**

Extend `test_controlled_heroes_inputs_reroute_to_hanu` (Task 2) with a final assertion:

```python
    assert run.latest_request.to_dict()["controlled_hero_id"] == "blue_enemy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/engine/effects/cases/test_hanu_effects.py -q -k reroute`
Expected: FAIL with `KeyError: 'controlled_hero_id'` (`to_dict` only surfaces selected keys).

- [ ] **Step 3: Implement**

3a. `src/goa2/domain/input.py` — in `to_dict()`, right after the base `result` dict is built (the one containing `"player_id"`):

```python
        # Controlled action (Hanu — The Ultimate Trick): player_id names the
        # controller; this names the hero whose action is being performed.
        if "controlled_hero_id" in self.context:
            result["controlled_hero_id"] = self.context["controlled_hero_id"]
```

3b. `docs/CLIENT_INTEGRATION_GUIDE.md` — add a short subsection in the input-request documentation:

```markdown
### Controlled actions (Hanu — The Ultimate Trick)

When Hanu's ultimate is active and Hurry Up! targeted a hero, that hero's next
action is decided by Hanu's player. During such an action, input requests for
the acting hero carry:

- `player_id`: the **controller's** hero id (e.g. `hero_hanu`) — this player
  must answer, and only their token is accepted.
- `controlled_hero_id`: the hero whose action is being performed.

Everything else is unchanged: options are computed relative to the controlled
hero (the controller can only pick choices that hero could legally make), and
requests addressed to other players (defenders, team choices) are unaffected.
Clients should render prompts as "<controller> is controlling <hero>" when
`controlled_hero_id` is present. This field only appears during controlled
actions; the change is additive.
```

- [ ] **Step 4: Run the full suite**

Run: `PYTHONPATH=src uv run pytest tests/ -q`
Expected: PASS (~1915 tests). Also: `uv run ruff check src/ && uv run black --check src/`
Expected: clean (run `uv run black src/` if formatting differs).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(hanu): surface controlled_hero_id to clients; document controlled actions"
```

---

## Self-Review Notes

- Spec coverage: rules 1-5 → Task 1 (gate/effect), Task 2 (remap, invariant, fizzle, rollback, defender untouched), Task 3 (client contract). Persistence via auto-union + `test_persistence.py` in Task 1 Step 4. Friendly-target case is behaviorally identical to enemy-target (the effect stores only ids); covered implicitly.
- The spec's `AnyStep` union edit is obsolete: `step_types.py` auto-builds the union from `GameStep` subclasses (enum value + subclass is the whole registration).
- `run.finish()` in Task 1 tests works because `run_card` defaults to `finalize_turn=False` — the stack drains after Hurry Up!'s steps without starting blue_enemy's turn.
