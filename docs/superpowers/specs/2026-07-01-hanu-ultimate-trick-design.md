# Hanu — The Ultimate Trick (Purple Ultimate) Design

**Date:** 2026-07-01
**Status:** Approved

## Card

> "You choose the next action, and how it is performed, for a hero you target with the 'Hurry Up!'."

Passive ultimate, auto-active at level 8 (no upgrade choice, no action of its own).
Currently registered as an inert placeholder (`the_ultimate_trick` in
`src/goa2/scripts/hanu_effects.py`); this spec replaces the placeholder with real behavior.

## Locked rules interpretations (approved 2026-07-01)

1. **Trigger — always on, any target.** Whenever Hanu (level ≥ 8) resolves Hurry Up!
   on a hero — friendly or enemy — control applies automatically. No confirmation prompt.
2. **Control scope — all inputs during the target's action window.** Every input
   addressed to the controlled hero while they are the current actor goes to Hanu's
   player: action-mode choice, movement, attack targets, optional effects, the hero's
   own passive confirmations, respawn placement (if they respawn to act), and the
   end-of-turn confirm/rollback. Team-level (`team:X`) prompts stay with the team.
   Prompts addressed to other players (defenders, tie-breakers) are untouched.
3. **Core invariant — only the decision-maker changes.** The actor remains the
   controlled hero. All legality — team relations, ranges, filters, stats,
   immunity — is computed relative to the controlled hero. Example: Pedro (Hanu)
   controlling Wuk cannot make Wuk attack Wuk's allies; Hanu's player can only choose
   among options Wuk's own player could have chosen.
4. **Fizzle — tied to that card, this round.** Control fires only when the hero acts
   to resolve the specific card that was UNRESOLVED when Hurry Up! hit them. If that
   card leaves the UNRESOLVED state any other way (discarded, cancelled, hero defeated
   before acting), or the round ends, control never fires. It never carries to a
   future round or a replacement card.
5. **Hanu's defeat does not cancel control.** The trick was set when Hurry Up!
   resolved; Hanu's player still makes the choices.

## Approach

**Handler-level `player_id` remap + control effect.** The engine sets
`state.current_actor_id` for the whole action window and nearly all input requests
carry `player_id = acting hero`; server auth (`validate_input_turn`) and WebSocket
broadcasts key off `InputRequest.player_id`. So control is implemented by rewriting
`player_id` at the single choke point where the handler returns an input request —
after all options/legality were already computed relative to the actor. This gives
the core invariant structurally and works identically for the REST server, WebSocket,
`GameSession`, the demo script, and tests.

Rejected alternatives: per-step controller threading (dozens of call sites, fragile
against future steps); server-layer auth remap (broadcasts prompt the wrong client;
non-server consumers get no control; violates engine self-containment).

## Components

| Piece | Location | Description |
|---|---|---|
| `EffectType.CONTROL_NEXT_ACTION` | `domain/models/effect.py` | New enum value |
| `ActiveEffect.controlled_card_id: str \| None` | `domain/models/effect.py` | New typed payload field (follows existing effect-specific field pattern, e.g. `split_axis`) |
| `ScheduleActionControlStep` | `engine/steps/effects.py`; new `StepType.SCHEDULE_ACTION_CONTROL` in `domain/models/enums.py`; added to `AnyStep` in `engine/step_types.py` | Reads `hurry_target` from context. No-ops unless the acting Hanu is level ≥ 8 and the target has an UNRESOLVED `current_turn_card`. Otherwise creates the control effect and emits `EFFECT_CREATED`. |
| Control effect instance | created via `EffectManager.create_effect` | `effect_type=CONTROL_NEXT_ACTION`, `source_id=<hanu>`, scope `POINT` on the target hero, `duration=THIS_ROUND`, `is_active=True`, `controlled_card_id=<target's current_turn_card.id>` |
| `HurryUpEffect` change | `scripts/hanu_effects.py` | Append `ScheduleActionControlStep(...)` after `SetCardInitiativeStep` (gate lives inside the step, at resolve time) |
| Handler remap | `engine/handler.py`, input-return block (`requires_input`) | See below |
| `TheUltimateTrickEffect` | `scripts/hanu_effects.py` | Remains a no-step passive; the behavior lives in Hurry Up!'s scheduling step. Docstring updated. |

### Handler remap logic

At the point where the handler is about to return an `InputRequest`:

1. If `request.player_id == str(state.current_actor_id)`, and
2. there is an active `CONTROL_NEXT_ACTION` effect whose scope targets that hero, and
3. the hero's `current_turn_card` exists with `id == effect.controlled_card_id`,

then rewrite `request.player_id` to the effect's `source_id` (Hanu) and set
`request.context["controlled_hero_id"] = <controlled hero id>`.

The existing rollback-disable branch ("input targets someone other than the current
actor → `rollback_disabled = True`") must NOT fire when the mismatch is caused by
this remap: Hanu receives the rerouted `ConfirmResolutionStep` and may roll back and
re-perform the controlled action. Order the remap and the rollback check so a
control-remap bypasses the disable (inputs to genuinely-other players still disable
rollback as today).

## Data flow

1. Hanu (level 8) plays Hurry Up! on Wuk → `SetCardInitiativeStep` sets initiative 11
   → `ScheduleActionControlStep` records the control effect with Wuk's card id.
2. Later, `resolve_next_action` selects Wuk as actor for that card
   (`state.current_actor_id = hero_wuk`; `ResolveCardStep` → `ConfirmResolutionStep`
   → `FinalizeHeroTurnStep` pushed).
3. Every input request produced during the action carries `player_id="hero_wuk"` →
   remapped at the handler to `player_id="hero_hanu"` with
   `context["controlled_hero_id"]="hero_wuk"`.
4. Server auth accepts only Hanu's token for these requests; broadcasts prompt Hanu's
   client. Options were computed relative to Wuk, so only Wuk-legal choices exist.
5. `FinalizeHeroTurnStep` resolves the card (leaves UNRESOLVED) — the guard can never
   match again. The effect expires with the round (`THIS_ROUND` cleanup), so the same
   card id re-played next round cannot false-match.

## Edge handling

- **Fizzle paths need no bespoke code:** card discarded → guard (card id + actor)
  fails; hero never acts → effect expires at end of round; card re-played next
  round → effect already expired.
- **Nested inputs to other players** (defense reactions, team tie-breakers,
  `team:X` decisions) have `player_id != current_actor_id` and are never remapped.
- **Respawn placement:** `RespawnHeroStep` runs inside the actor window, so its input
  reroutes to Hanu (per locked rule 2).
- **Hanu defeated before Wuk acts:** effect persists (rule 5); nothing to do.

## Client contract impact (additive only)

- `InputRequest.player_id` may name a hero other than the current actor during a
  controlled action.
- `InputRequest.context` may contain `controlled_hero_id`.
- `EFFECT_CREATED` event (metadata: `effect: "action_control"`, controller, target,
  card id) announces control when Hurry Up! resolves.
- No new request types, response shapes, or endpoints. Add a short section to
  `docs/CLIENT_INTEGRATION_GUIDE.md`.

## Persistence

New `StepType` + `AnyStep` union entry for `ScheduleActionControlStep`. The control
effect is a plain `ActiveEffect` (new enum value + new optional field), so it
round-trips through existing serialization. No new filter types.

## Testing (TDD, in `tests/engine/effects/cases/test_hanu_effects.py` + handler-level coverage)

1. Level 8 Hanu resolves Hurry Up! on an enemy → `CONTROL_NEXT_ACTION` effect exists
   with the target's card id; below level 8 → no effect (initiative 11 still applies).
2. Controlled hero acts → input requests carry Hanu's `player_id` and
   `controlled_hero_id` in context.
3. **Invariant:** controlled hero's attack-target options exclude their own allies
   (legality relative to the controlled hero, not Hanu).
4. Fizzle: card discarded before acting → no remap when the hero would act; end of
   round → effect gone; same card played next round → no remap.
5. During the controlled turn, an input addressed to another player (e.g., defender's
   defense-card window) is not remapped.
6. Friendly-hero target: control applies identically.
7. Rollback: Hanu can roll back the controlled action via the rerouted
   `ConfirmResolutionStep` (`rollback_disabled` not set by the control remap).
8. Persistence: step and effect serialize/deserialize (round-trip).
