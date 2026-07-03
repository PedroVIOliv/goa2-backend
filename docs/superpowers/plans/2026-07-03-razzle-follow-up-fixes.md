# Razzle Multipiece Follow-up Fixes

**Date:** 2026-07-03
**Status:** COMPLETED 2026-07-03 (commit b46d2a4) — all guard tests and the full suite pass

## Goal

Finish the finite integration gaps in the stable `HeroPiece` architecture.
Keep the current model: `hero_razzle` is player-level only, while board
presence is represented by stable `hero_razzle_piece_1..4` entities.

Do not migrate to anchor swap. Anchor swap would mask some compatibility bugs,
but it reintroduces hidden identity movement and persistent-binding risk. The
remaining work is to centralize the player-vs-board identity boundary.

## Boundary Rules

1. Board-level hero checks must treat `HeroPiece` as a hero unit.
   This includes targeting, auras, action prevention, terrain rules, adjacency,
   and "each enemy hero" style effects.

2. Player-level ownership must normalize `HeroPiece` IDs to their owner hero.
   This includes hand, deck, discard, gold, auth, and `player_id` routing for
   input prompts. Board-attached stat markers are not player-level ownership;
   see the stat semantics below.

3. Razzle card resolution must use the bound acting piece for authoritative
   positional stats and origins. Preview values may remain approximate, but
   actual resolution must not compute area-sensitive stats from `hero_razzle`
   when that ID has no board position.

4. Persistent positional bindings created by Razzle must store stable piece IDs,
   not the owner hero ID, whenever the binding refers to a board location.

## Governing Principle (authoritative)

While no card or action is being resolved (initiative counting, turn-order
decisions, end-of-round bookkeeping), all Razzle pieces count as **one hero**.

Whenever anyone — Razzle or an opponent — is acting or resolving a card, each
Razzle piece counts as a **different hero** for all purposes *except*
player-level state: hand, deck, discard, played/current-turn card, gold, items,
level, lives/defeat status, and auth/prompt routing.

The mode switch is keyed on "is a card being resolved right now", not on
"is a Razzle piece the actor". During an *enemy's* resolution, Razzle pieces
are still distinct heroes (each can be targeted, each counts for
"each enemy hero", each provides adjacency/support independently).

## Stat Semantics for Razzle

The engine models the principle with two stat modes:

1. **Resolution mode (action/defense):** any card is resolving and a specific
   board piece is acting, attacking, defending, moving, or being targeted.
   Compute positional stats and board-attached markers from that piece only.

2. **Initiative mode:** no card is resolving; Razzle is one hero with multiple
   board presences. Compute initiative from the owner hero plus the union of all
   effects/markers touching any Razzle piece. Count each distinct effect or
   marker once, even if it touches multiple pieces.

Initiative is derived from the shared turn card, so it is always an owner-level
aggregate stat — even if some effect reads initiative mid-resolution, use the
initiative-mode aggregation, never a single piece's position.

Examples:

- One Tali Ice token adjacent to two Razzle pieces gives Razzle `-1`
  initiative, not `-2`.
- One Ice token adjacent to one piece and two different Ice tokens adjacent to
  another piece gives Razzle `-3` initiative.
- Two Ice tokens adjacent to one piece, where one of those tokens is also
  adjacent to another Razzle piece, gives Razzle `-2` initiative.
- A Poison marker on one Razzle piece gives that piece `-2` attack/defense, but
  unpoisoned pieces do not inherit that attack/defense penalty. Razzle's
  initiative still gets the Poison marker's initiative penalty once.
- Trinkets Barrier tokens are positional defense auras: one piece near one
  Barrier has `+1` defense, another piece near two Barriers has `+2` defense.
  They do not combine into `+3` defense for every piece.

## Known Fixes

### 1. Hero-like board checks

Add or reuse a small helper such as `is_hero_unit(entity)` and replace scattered
`isinstance(entity, Hero)` checks in board-positional logic.

Known files:

- `src/goa2/engine/validation_effects.py`
- `src/goa2/engine/validation_terrain.py`
- `src/goa2/engine/filters_units.py`
- `src/goa2/engine/filters_hex.py`

Guard tests:

- `AffectsFilter.ENEMY_HEROES` matches an enemy Razzle piece.
- Static Barrier applies when the acting board unit is a Razzle piece.
- A filter asking for adjacency to a hero counts adjacent Razzle pieces.
- Brynn-style hero obstacle logic counts enemy Razzle pieces.
- Razzle pieces treat each other as different heroes during resolution: a
  Razzle card referencing "another hero" or "an adjacent hero" can select her
  own other piece.

### 2. Player/input normalization

Normalize any context-derived piece ID before using it as an input `player_id`.
The player who answers a prompt must be `hero_razzle`, not
`hero_razzle_piece_N`.

Known file:

- `src/goa2/engine/steps/selection.py`

Guard tests:

- A forced discard targeting `hero_razzle_piece_N` displays cards from Razzle's
  hand and routes the prompt to `hero_razzle`.
- The server accepts the Razzle player's token for that prompt.

### 3. Acting-piece stats, initiative aggregation, and origins

When resolving a primary card, compute authoritative stats using
`state.resolve_board_actor(hero.id)` after `ChooseActingPieceStep` has bound a
piece. When resolving defense or on-block text, use the attacked piece from the
combat context when available.

When computing initiative for a multi-piece hero, aggregate across all live
pieces. Apply each distinct positional stat effect once if at least one piece is
in scope. Do not compute initiative from `hero_razzle`'s position, because the
owner hero has no board location.

Known files:

- `src/goa2/engine/effects.py`
- `src/goa2/engine/stats.py`
- `src/goa2/engine/phases.py`
- `src/goa2/domain/views.py`

Guard tests:

- An area stat modifier near only the acting piece changes Razzle's resolved
  card value.
- The same modifier near another piece does not affect the action.
- Defense stats/radius calculations use `context["defender_id"]` when the
  defender is a Razzle piece.
- Initiative from Tali Ice tokens counts each Ice token once if any Razzle piece
  is adjacent, even when one token touches multiple pieces.
- Trinkets Barrier defense bonuses remain piece-local for defense calculations.

### 4. Piece-local stat markers with owner-level initiative aggregation

Do not normalize stat marker targets from `HeroPiece` to owner hero at placement
time. A marker placed on a Razzle piece should remain attached to that board
piece for action/defense stats. Initiative should aggregate markers across all
pieces and count each marker once.

**This reverses an earlier ruling.** `state.place_marker()` currently
normalizes HeroPiece targets to the owner hero (docstring cites the old
ruling), and
`tests/engine/pieces/test_position_resolver.py::test_place_marker_on_piece_attaches_to_hero`
pins that behavior. Both must be updated, along with the `Marker` docstring's
"placed on heroes" framing.

Defeat-triggered and cleanup semantics stay owner-level: any-piece defeat
cascades to hero defeat, so BOUNTY-style markers pay out once for the hero, and
"markers on defeated heroes return to supply" must match a marker whose
`target_id` is any piece of the defeated hero.

Known files:

- `src/goa2/domain/state.py`
- `src/goa2/engine/steps/markers.py`
- `src/goa2/engine/stats.py`
- `src/goa2/domain/views.py`

Guard tests:

- Tigerclaw Poisoned Dart targeting `hero_razzle_piece_2` gives that piece `-2`
  attack and `-2` defense.
- An unpoisoned Razzle piece does not inherit the poisoned piece's attack or
  defense penalty.
- Razzle's initiative includes the Poison marker's initiative penalty once.
- Marker cleanup on defeat/end of round still returns a marker attached to a
  Razzle piece.

### 5. Stable persistent bindings

Any step that creates a persistent positional effect or delayed by-ID binding
from Razzle should store the acting piece ID for board location semantics.

Known files to audit:

- `src/goa2/engine/steps/effects.py`
- Any future Razzle card effects that create `ActiveEffect`, delayed return, or
  by-ID follow-up steps.

Guard tests:

- A persistent point/radius effect created by Razzle remains anchored to the
  piece that created it after Razzle acts with a different piece.
- A delayed return/swap effect targeting a Razzle piece returns the same physical
  piece, not whichever piece acted later.

## Stop Condition

This is complete when the guard tests above pass and the full suite passes:

```bash
PYTHONPATH=src uv run pytest tests/ -q
```

After that, remaining Razzle issues should be treated as normal card-specific
bugs, not open-ended multipiece infrastructure uncertainty.
