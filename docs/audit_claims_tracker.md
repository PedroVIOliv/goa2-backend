# GoA2 Backend Audit Claims Tracker

Source audit date: 2026-06-04
Initial test baseline from audit: `1479 passed, 0 failed`
Created: 2026-06-05

This file tracks the claims from the full-repo audit and whether each one has been resolved, rejected, deferred, or still needs work.

## Status Legend

- `Open`: Claim still needs investigation or a fix.
- `In progress`: Work has started but is not complete.
- `Resolved`: Fix has landed and relevant tests/docs have been updated.
- `Not reproducible`: Claim was investigated and could not be reproduced.
- `Deferred`: Valid claim, intentionally postponed.
- `Needs decision`: Facts are known, but the team needs to decide expected behavior.

When closing a claim, update `Status`, `Resolution notes`, and add the fixing PR, commit, or test name where possible.

## Audit Metadata

| ID | Status | Claim | Resolution notes |
|---|---|---|---|
| A1 | Open | `scripts-effects-A` reviewer failed to return structured output, so whisper, mortimer, ursafar, rowenna, and tigerclaw `_effects.py` were not directly reviewed. | Re-run targeted review before closing the audit. |

## High Severity

| ID | Status | Claim | Primary location(s) | Resolution notes |
|---|---|---|---|---|
| H1 | Resolved | `GameStep.should_skip()` treats `False` as "run", so `active_if_key` gates fire when they should skip. Affects Ursafar `block_succeeded` and Arien Ebb and Flow `can_repeat`. | `src/goa2/engine/steps/base.py`; `src/goa2/engine/steps/combat.py`; `src/goa2/engine/steps/utility.py`; `src/goa2/scripts/ursafar_effects.py`; `src/goa2/scripts/arien_effects.py` | `active_if_key` now skips on falsy values. Added a direct `False` regression and corrected Ebb and Flow distant-target expectation. |
| H2 | Open | Trinkets is registered/selectable, but 17 of 18 card effects reference unregistered `effect_id`s and silently no-op. | `src/goa2/data/heroes/trinkets.py`; `src/goa2/scripts/trinkets_effects.py` | Implement/register missing effects or unregister the hero until complete. Add registry-walk test. |
| H3 | Resolved | `MultiSelectStep` accepts client-submitted selections without validating they are in the offered candidate set. | `src/goa2/engine/steps/selection.py` | Submitted ids are now validated against `_get_candidates()` before being accepted; invalid ids are dropped and input re-requested (mirrors `SelectStep`). Also guarded `DONE`/`SKIP` from finishing below `min_selections`. Regressions: `TestMultiSelectStep::test_rejects_selection_outside_candidate_set`, `::test_rejects_done_below_min_selections`. Same validate-against-offered-set pattern still pending for M6/M7. |
| H4 | Resolved | `find_nearest_empty_hexes()` returns terrain/wall hexes as valid placement targets because it checks occupancy only. | `src/goa2/engine/map_logic.py`; callers in `src/goa2/engine/steps/combat.py` and `src/goa2/engine/steps/movement.py` | Candidate check now uses `not tile.is_obstacle` (terrain or occupant). Latent only — shipped `forgotten_island.json` has no in-zone terrain, so no live bug today. Regression: `test_find_nearest_empty_hexes_skips_terrain`. |
| H5 | Open | Winner is lost to all clients after a finished game is restored from disk because `last_result` is not rebuilt for a stackless `GAME_OVER` state. | `src/goa2/engine/persistence.py`; `src/goa2/server/routes_games.py`; `src/goa2/server/ws.py` | Rebuild `last_result` on load or surface `state.winner` in views/responses. |
| H6 | Open | Unauthenticated game creation can exhaust memory, disk, and file descriptors through unlimited `POST /games`. | `src/goa2/server/routes_games.py`; `src/goa2/server/registry.py`; `src/goa2/server/app.py` | Add creation cap/rate limit/shared secret and cleanup/eviction behavior. |

## Medium Severity

| ID | Status | Claim | Primary location(s) | Resolution notes |
|---|---|---|---|---|
| M1 | Open | Facedown enemy mine masks `token_type` and name but leaks real `owner_id`. | `src/goa2/domain/views.py`; `tests/domain/test_views_tokens.py` | Hide `owner_id` when token is hidden; add assertions. |
| M2 | Open | `map_name` builds a filesystem path without containment checks, creating path traversal/existence-oracle behavior. | `src/goa2/server/routes_games.py`; `src/goa2/server/models.py` | Reject separators/`..` or enforce `commonpath` under maps directory. |
| M3 | Open | Per-game `FileHandler` is never closed on game removal or stale cleanup. | `src/goa2/server/registry.py`; `src/goa2/server/game_logger.py` | Close `GameLogger` before dropping games and remove named logger if needed. |
| M4 | Open | Input contract advertises `request_id`, but `InputRequest.to_dict()` omits it and `submit_input()` ignores it. | `src/goa2/engine/handler.py`; `src/goa2/domain/input.py` | Emit id and validate request id, or remove the field from contract. |
| M5 | Open | Several ranged attacks omit `is_ranged=True`, so anti-ranged defenses fail to block them. | `src/goa2/scripts/dodger_effects.py`; `src/goa2/scripts/wasp_effects.py` | Add `is_ranged=True` for Burning Skull, Charged Boomerang, and Thunder Boomerang attacks. |
| M6 | Open | `ChooseMinionRemovalStep` removes any client-chosen unit without checking it was offered, bypassing heavy-minion protection. | `src/goa2/engine/steps/selection.py` | Validate selected id against `_get_valid_choices()`. |
| M7 | Open | `ResolveTieBreakerStep` accepts unvalidated `winner_id` and can make an invalid hero the active actor. | `src/goa2/engine/steps/selection.py` | Validate winner id is in tied candidates and handle missing heroes. |
| M8 | Open | Flurry of Blows makes optional repeat attack mandatory, which can abort the whole turn. | `src/goa2/scripts/min_effects.py` | Set repeat attack mandatory flag to false; update locked-in test. |
| M9 | Open | Xargatha charm/control/dominate after-movement destination uses Xargatha reachability instead of the minion's. | `src/goa2/scripts/xargatha_effects.py` | Use `unit_key` for the after-selected minion context key. |
| M10 | Open | Respawn hero/minion and lane-push mutate observable board state without emitting `GameEvent`s. | `src/goa2/engine/steps/combat.py` | Emit `UNIT_PLACED`/`UNIT_REMOVED` events and add tests. |
| M11 | Open | `expire_by_source` and `expire_by_card` silently drop `DELAYED_TRIGGER` finishing steps. | `src/goa2/engine/effect_manager.py`; caller in `src/goa2/engine/steps/combat.py` | Collect/return finishing steps or make non-firing behavior explicit. |
| M12 | Open | `TopologyService.are_connected()` ignores effect `is_active` and duration. | `src/goa2/engine/topology.py` | Gate topology effects through shared active/duration checks. |
| M13 | Open | WebSocket broadcast can crash if connections mutate while iterating during awaited sends. | `src/goa2/server/ws.py` | Snapshot connections before iterating or mutate under the game lock. |
| M14 | Open | Same token connecting twice overwrites the active socket; stale disconnect can remove the current socket from broadcasts. | `src/goa2/server/ws.py` | Store multiple sockets per token or evict/guard by socket identity. |

## Low Severity

| ID | Status | Claim | Primary location(s) | Resolution notes |
|---|---|---|---|---|
| L1 | Open | `RelativeDistanceFilter` treats topology-disconnected candidates as passing for comparison operators such as `>`/`>=`/`==`. | `src/goa2/engine/filters_geometry.py` | Align disconnected-distance behavior with `RangeFilter`. |
| L2 | Open | Trinkets `salvage_parts` "move up to 3" omits `MovementPathFilter`, offering unreachable destinations. | `src/goa2/scripts/trinkets_effects.py` | Add path validation before moving. |
| L3 | Open | PASSIVE card-bound effects are never cleaned up after the card leaves play. | `src/goa2/engine/effect_manager.py` | Define and implement cleanup behavior. |
| L4 | Open | `MayRepeatOnceStep.steps_template` is not re-annotated to `list[AnyStep]`, so direct dumps can drop nested step data. | `src/goa2/engine/step_types.py`; `src/goa2/engine/steps/utility.py` | Patch field annotation/model rebuild if direct dumps remain supported. |
| L5 | Open | `CardEffectRegistry.register` silently overwrites duplicate `effect_id`s. | `src/goa2/engine/effects.py` | Reject duplicate registrations. |
| L6 | Open | Stale Knight hero stub references 3 unregistered effect ids if it is ever imported and registered. | `src/goa2/data/heroes/knight.py` | Keep excluded or implement/remove stale ids. |
| L7 | Open | `LineBehindTargetFilter` Hex branch is dead code because entity lookup happens first. | `src/goa2/engine/filters_geometry.py` | Simplify or fix branch ordering if Hex input is intended. |
| L8 | Open | Malformed `CHEATS_GOLD` WebSocket payload raises uncaught `TypeError` and drops the player's socket. | `src/goa2/server/ws.py` | Validate numeric payload and return protocol error. |
| L9 | Open | Crane/Tiger/Dragon Stance "up to N" push uses a mandatory target select, contradicting the optional push. | `src/goa2/scripts/min_effects.py` | Make target select optional or otherwise model "up to N" directly. |
| L10 | Open | Movement-action validation cannot honor `except_card_colors` at execution time because `context['card']` is absent. | `src/goa2/engine/validation_actions.py` | Decide whether execution-time re-check needs card context. |

## Test Gaps

| ID | Status | Gap | Primary location(s) | Resolution notes |
|---|---|---|---|---|
| T1 | Resolved | No test asserts `active_if_key` skips when the value is `False`; one Ebb and Flow test codifies the bug. | `tests/engine/test_ursafar_group_a.py`; `tests/engine/test_ebb_and_flow.py` | Added direct `active_if_key=False` coverage and corrected Ebb and Flow distant-target expectation. |
| T2 | Open | No global test walks `HeroRegistry` and verifies every card `effect_id` resolves to a registered effect. | `tests/` | Add registry completeness test. |
| T3 | Open | `expire_active_turn_effects` NEXT_TURN boundary and cross-round timing are untested. | `src/goa2/engine/effect_manager.py` | Add boundary tests. |
| T4 | Resolved | No test rejects invalid filtered-out selections for `MultiSelectStep`. | `tests/engine/test_steps.py` | Added `TestMultiSelectStep::test_rejects_selection_outside_candidate_set` (filtered-out id) and `::test_rejects_done_below_min_selections`. |

## Contested Claims

| ID | Status | Claim | Primary location(s) | Decision needed |
|---|---|---|---|---|
| C1 | Needs decision | Starting cards live in both `hero.deck` and `hero.hand` as the same object. Verifiers agreed on facts but disagreed whether this is intentional master-card-pool behavior or a client-view duplication/leak. | `src/goa2/domain/models/unit.py`; `src/goa2/engine/setup.py`; `src/goa2/domain/views.py` | Decide deck model and test the player/opponent deck view. |
| C2 | Needs decision | `GameState.place_entity` can record off-map positions if called directly, but current traced callers appear not to reach this path. | `src/goa2/domain/state.py` | Decide whether to add defensive on-map validation. |
| C3 | Needs decision | Handler drops `StepResult.new_steps` when `requires_input` or `abort_action` is also set, but no current call sites combine those fields. | `src/goa2/engine/handler.py` | Decide whether to assert/disallow that combination or support it. |

## Recommended Follow-ups

| ID | Status | Follow-up | Resolution notes |
|---|---|---|---|
| F1 | Resolved | Sweep every `active_if_key` consumer and producer for bool-`False` producers beyond `block_succeeded` and `can_repeat`. | Global gate now skips all falsy context values; full test suite passes with the new contract. |
| F2 | Open | Systematically review input-content validation for every input type, not only the confirmed invalid-selection cases. | Include `SELECT_NUMBER`, `SELECT_OPTION`, `CHOOSE_ACTION`, and `SELECT_HEX`. |
| F3 | Open | Audit every `AttackSequenceStep` across hero scripts against each card's `is_ranged` field. | Add a regression test if practical. |
| F4 | Open | Add a global hero-data completeness test for all production heroes. | Likely overlaps T2. |
| F5 | Open | Add a WebSocket concurrency integration harness for connect/disconnect/broadcast races. | Covers M13 and M14. |
| F6 | Open | Re-verify topology subsystem behavior when Nebkher or topology-effect heroes ship. | Covers M12 and L1. |
| F7 | Open | Re-audit `build_view()` player scoping beyond token `owner_id`, including facedown cards, markers, effects, and modifiers. | Add leak tests for any exposed fields. |
| F8 | Open | Add persistence property tests for dump/validate/dump idempotence. | Especially useful for nested step/filter unions. |
| F9 | Open | Examine auth token generation and comparison for entropy and timing behavior. | No issue confirmed in audit. |
| F10 | Open | Re-run review of whisper, mortimer, ursafar, rowenna, and tigerclaw effect scripts. | Same coverage gap as A1. |
| F11 | Resolved | Update Ursafar Prey Drive / Prey Abundance / Feeding Frenzy to gate on whether the attack target remains on the board, not `block_succeeded`. | Added `CheckUnitOnBoardStep` and gated Ursafar's bonus removal on `target_not_removed`. Regression tests cover removed targets, Brogan-protected targets, and Feeding Frenzy step construction. |
